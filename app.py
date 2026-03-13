import streamlit as st
import pandas as pd
import math
import base64
import requests
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

# --- 1. 기본 설정 및 유틸리티 ---
st.set_page_config(page_title="스펀지 단가 산출 TOOL (v-Management)", layout="wide")

st.markdown("""
    <style>
    input[::-webkit-outer-spin-button], input[::-webkit-inner-spin-button] { -webkit-appearance: none; margin: 0; }
    input[type=number] { -moz-appearance: textfield; }
    button[data-testid="stNumberInputStepUp"], button[data-testid="stNumberInputStepDown"] { display: none; }
    </style>
    """, unsafe_allow_html=True)

def excel_round(number, decimals=0):
    if pd.isna(number) or number is None: return 0
    multiplier = 10 ** decimals
    return float(Decimal(str(float(number) * multiplier)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) / multiplier

def excel_rounddown(number, decimals=0):
    if pd.isna(number) or number is None: return 0
    multiplier = 10 ** decimals
    return math.floor(float(number) * multiplier) / multiplier

def update_github_file(content):
    try:
        token = st.secrets["GITHUB_TOKEN"]
        repo = st.secrets["REPO_NAME"]
        path = st.secrets["FILE_PATH"]
        url = f"https://api.github.com/repos/{repo}/contents/{path}"
        headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
        res = requests.get(url, headers=headers)
        sha = res.json().get('sha') if res.status_code == 200 else None
        encoded_content = base64.b64encode(content.encode('utf-8-sig')).decode('utf-8')
        data = {"message": f"Update DB: {datetime.now().strftime('%Y-%m-%d %H:%M')}", "content": encoded_content, "sha": sha}
        return requests.put(url, headers=headers, json=data).status_code in [200, 201]
    except: return False

# --- 2. 데이터 로드 (버전 컬럼 대응) ---
@st.cache_data
def fetch_raw_data():
    for enc in ['utf-8-sig', 'cp949', 'euc-kr']:
        try:
            df = pd.read_csv('spongematerials.csv', encoding=enc)
            df.columns = df.columns.str.strip().str.replace(' ', '')
            
            # [신규] '버전' 컬럼이 없으면 '기본'으로 생성하여 오류 방지
            if '버전' not in df.columns:
                df.insert(0, '버전', '기본')
            
            for col in ['가공업체단가', '발포업체단가']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', ''), errors='coerce').fillna(0.0)
            return df
        except: continue
    return pd.DataFrame(columns=['버전', '재질', '밀도', '경도', '발포업체', '가공업체단가', '발포업체단가'])

if "master_db" not in st.session_state:
    st.session_state.master_db = fetch_raw_data()

if "input_df" not in st.session_state:
    st.session_state.input_df = pd.DataFrame([{"선택업체": "진양", "재질": "선택하세요", "재단방식": "일반", "W(사선)": None, "W": None, "D": None, "T": None}])

if "last_result" not in st.session_state:
    st.session_state.last_result = None

if "calc_history" not in st.session_state:
    st.session_state.calc_history = {}

# --- 3. 화면 구성 ---
tab1, tab2 = st.tabs(["🧽 단가 산출", "🗂️ 재질 DB 관리"])

# [Tab 2: DB 관리] 모든 버전의 데이터를 수정/추가합니다.
with tab2:
    st.subheader("📋 재질 DB")
    st.info("단가가 변경되는 경우, 행을 추가하여 신규 버전 및 단가 내용을 입력하세요.")
    st.info("25.09: 진양 통합으로 인한 단가 인하 / 23.11: 제3유에프 단가 산정 시 사용")
    edited_master = st.data_editor(st.session_state.master_db, num_rows="dynamic", use_container_width=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🚀 현재 계산기에 반영 (임시)", use_container_width=True):
            st.session_state.master_db = edited_master
            st.success("반영되었습니다.")
    with c2:
        if st.button("🌐 DB 저장", use_container_width=True):
            if update_github_file(edited_master.to_csv(index=False)):
                st.success("GitHub 업데이트 성공!"); st.cache_data.clear()
            else: st.error("GitHub 업데이트 실패. Secrets를 확인하세요.")

# [Tab 1: 단가 산출] 특정 버전을 선택하여 계산합니다.
with tab1:
    st.title("🧽 스펀지 단가 산출 TOOL")
    
    # [신규] 버전 선택 드롭다운
    available_versions = sorted(st.session_state.master_db['버전'].unique().tolist())
    selected_ver = st.selectbox("📌 적용할 단가 버전 선택", available_versions, index=len(available_versions)-1)
    
    # 선택된 버전만 필터링한 데이터프레임 생성
    current_prices = st.session_state.master_db[st.session_state.master_db['버전'] == selected_ver]
    
    col_sys = st.columns(5)
    h_cut = col_sys[0].number_input("수평재단비", value=21.0, format="%.1f")
    v_cut = col_sys[1].number_input("수직재단비", value=11.0, format="%.1f")
    loss = col_sys[2].number_input("로스율(%)", value=5.0) / 100
    adm = col_sys[3].number_input("관리비(%)", value=5.0) / 100
    pro = col_sys[4].number_input("이윤(%)", value=10.0) / 100
    
    st.subheader(f"📝 목록 입력 ({selected_ver} 기준)")
    m_list = ["선택하세요"] + sorted(current_prices['재질'].dropna().unique().tolist())
    edited_df = st.data_editor(
        st.session_state.input_df, num_rows="dynamic", use_container_width=True,
        column_config={
            "선택업체": st.column_config.SelectboxColumn("선택업체", options=["진양", "폼웍스"], default="진양", required=False),
            "재질": st.column_config.SelectboxColumn("재질", options=m_list),
            "재단방식": st.column_config.SelectboxColumn("재단방식", options=["일반", "2D", "사선", "몰드"]),
        },
        key="editor_tab1"
    )

    def calc_engine(row):
        if any(pd.isna(row[c]) or str(row[c]).strip() == "" for c in ["W", "D", "T"]) or row['재질'] == "선택하세요":
            return pd.Series(["-", "-", 0, 0, 0, 0], index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])
        
        # [수정] 선택된 버전의 데이터(current_prices) 내에서만 검색
        m_info = current_prices[current_prices['재질'] == row['재질']]
        if m_info.empty: return pd.Series(["-", "-", 0, 0, 0, 0], index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])

        is_foam = (row['선택업체'] == "폼웍스")
        u_p = float(m_info['발포업체단가' if is_foam else '가공업체단가'].values[0])
        ws, w, d, t = float(row.get('W(사선)', 0) or 0), float(row['W']), float(row['D']), float(row['T'])

        af_q = (((ws + w) * d * t) / 918090) / 2 if row['재단방식'] == "사선" else (w * d * t) / 918090
        ah_m = excel_round(excel_round(af_q * u_p, 0) * (1.0 + (0 if is_foam else loss)), 0)
        
        ai_p_r = 0.0
        if row['재단방식'] == "2D": ai_p_r = ah_m * 0.2
        elif not is_foam:
            if row['재단방식'] == "일반": ai_p_r = (w/1000 * d/1000 * h_cut) + (w/1000 * d/1000 * t * v_cut)
            elif row['재단방식'] == "사선": ai_p_r = ((ws + w)/1000 * d/1000 * v_cut * t) + (w/1000 * d/1000 * h_cut)
        ai_p = excel_round(ai_p_r, 0)

        total = ah_m + ai_p + (ai_p * 0.1) + ((ah_m + ai_p + (ai_p * 0.1)) * adm)
        total += (ai_p + (ai_p * 0.1) + ((ah_m + ai_p + (ai_p * 0.1)) * adm)) * pro
        final = excel_rounddown(total, -1) if is_foam else excel_round(total, -1)
        
        return pd.Series([m_info['밀도'].values[0], m_info['경도'].values[0], excel_round(af_q, 2), int(ah_m), int(ai_p), int(final)], 
                         index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])

    if st.button("🚀 최종 단가 산출하기", use_container_width=True):
        results = edited_df.apply(calc_engine, axis=1)
        st.session_state.last_result = pd.concat([edited_df, results], axis=1)

    if st.session_state.last_result is not None:
        st.subheader("📊 결과 리스트")
        st.dataframe(st.session_state.last_result, use_container_width=True)
        # (히스토리 저장 및 CSV 다운로드 로직 동일)



