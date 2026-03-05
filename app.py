import streamlit as st
import pandas as pd
import math
import base64
import requests
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

# --- 1. 기본 설정 및 유틸리티 ---
st.set_page_config(page_title="스펀지 산출 및 DB 관리 TOOL", layout="wide")

st.markdown("""
    <style>
    input[::-webkit-outer-spin-button], input[::-webkit-inner-spin-button] { -webkit-appearance: none; margin: 0; }
    input[type=number] { -moz-appearance: textfield; }
    button[data-testid="stNumberInputStepUp"], button[data-testid="stNumberInputStepDown"] { display: none; }
    </style>
    """, unsafe_allow_html=True)

# 엑셀 방식 사사오입 함수
def excel_round(number, decimals=0):
    if pd.isna(number) or number is None: return 0
    multiplier = 10 ** decimals
    return float(Decimal(str(float(number) * multiplier)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) / multiplier

# 엑셀 방식 내림 함수
def excel_rounddown(number, decimals=0):
    if pd.isna(number) or number is None: return 0
    multiplier = 10 ** decimals
    return math.floor(float(number) * multiplier) / multiplier

# [에러 방지] 안전한 숫자 변환 함수
def safe_float(val):
    try:
        if pd.isna(val) or val is None or str(val).strip() == "":
            return 0.0
        return float(val)
    except:
        return 0.0

# GitHub 업데이트 함수
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
        return requests.put(url, headers=headers, json=data).status_code == 200
    except: return False

# --- 2. 데이터 로드 및 상태 관리 ---
@st.cache_data
def fetch_raw_data():
    for enc in ['utf-8-sig', 'cp949', 'euc-kr']:
        try:
            df = pd.read_csv('spongematerials.csv', encoding=enc)
            df.columns = df.columns.str.strip().str.replace(' ', '')
            for col in ['가공업체단가', '발포업체단가']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', ''), errors='coerce').fillna(0.0)
            return df
        except: continue
    return pd.DataFrame(columns=['재질', '밀도', '경도', '가공업체단가', '발포업체단가'])

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

with tab2:
    st.subheader("📋 마스터 재질 리스트 관리")
    edited_master = st.data_editor(st.session_state.master_db, num_rows="dynamic", use_container_width=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🚀 현재 계산기에 즉시 반영", use_container_width=True):
            st.session_state.master_db = edited_master
            st.success("반영되었습니다.")
    with c2:
        if st.button("🌐 GitHub에 영구 저장 (Commit)", use_container_width=True):
            if update_github_file(edited_master.to_csv(index=False)):
                st.success("GitHub 업데이트 성공!"); st.cache_data.clear()
            else: st.error("GitHub 업데이트 실패. Secrets를 확인하세요.")

with tab1:
    st.title("🧽 스펀지 단가 산출 TOOL")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: h_cut = st.number_input("수평재단비(원)", value=21.0, format="%.1f")
    with col2: v_cut = st.number_input("수직재단비(원)", value=11.0, format="%.1f")
    with col3: loss_rate = st.number_input("로스율(%)", value=5.0, format="%.1f") / 100
    with col4: admin_rate = st.number_input("관리비(%)", value=5.0, format="%.1f") / 100
    with col5: profit_rate = st.number_input("이윤(%)", value=10.0, format="%.1f") / 100
    st.write("---")

    st.subheader("📝 목록 입력")
    material_list = ["선택하세요"] + sorted(st.session_state.master_db['재질'].dropna().unique().tolist())
    edited_df = st.data_editor(
        st.session_state.input_df, num_rows="dynamic", use_container_width=True,
        column_config={
            "선택업체": st.column_config.SelectboxColumn("선택업체", options=["진양", "폼웍스"], default="진양", required=False),
            "재질": st.column_config.SelectboxColumn("재질", options=material_list),
            "재단방식": st.column_config.SelectboxColumn("재단방식", options=["일반", "2D", "사선", "몰드"]),
            "W(사선)": st.column_config.NumberColumn("W(사선)", format="%d"),
            "W": st.column_config.NumberColumn("W", format="%d"),
            "D": st.column_config.NumberColumn("D", format="%d"),
            "T": st.column_config.NumberColumn("T", format="%d"),
        }
    )

    def calculate_row(row):
        # [수정] 빈칸을 0으로 안전하게 인식하도록 safe_float 적용
        if any(pd.isna(row[col]) or str(row[col]).strip() == "" for col in ["W", "D", "T"]) or row['재질'] == "선택하세요":
            return pd.Series(["-", "-", 0, 0, 0, 0], index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])
        
        vol_unit = 918090 
        mat_info = st.session_state.master_db[st.session_state.master_db['재질'] == row['재질']]
        if mat_info.empty: return pd.Series(["-", "-", 0, 0, 0, 0], index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])

        is_foam_company = (row['선택업체'] == "폼웍스") # 엑셀 수식 기반 (발포업체=ROUNDDOWN)
        u_price = float(mat_info['발포업체단가' if is_foam_company else '가공업체단가'].values[0])
        ws, w, d, t = safe_float(row['W(사선)']), safe_float(row['W']), safe_float(row['D']), safe_float(row['T'])

        # 엑셀 방식 정밀 합산
        af_qty = (((ws + w) * d * t) / vol_unit) / 2 if row['재단방식'] == "사선" else (w * d * t) / vol_unit
        ah_mat = excel_round(excel_round(af_qty * u_price, 0) * (1.0 + (0 if is_foam_company else loss_rate)), 0)
        
        ai_proc_raw = 0.0
        if row['재단방식'] == "2D": ai_proc_raw = ah_mat * 0.2
        elif not is_foam_company: # 가공업체일 때만 가공비 발생
            if row['재단방식'] == "일반": ai_proc_raw = (w/1000 * d/1000 * h_cut) + (w/1000 * d/1000 * t * v_cut)
            elif row['재단방식'] == "사선": ai_proc_raw = ((ws + w)/1000 * d/1000 * v_cut * t) + (w/1000 * d/1000 * h_cut)
        ai_proc = excel_round(ai_proc_raw, 0)

        aj_exp = ai_proc * 0.1
        ak_admin = (ah_mat + ai_proc + aj_exp) * admin_rate
        al_profit = (ai_proc + aj_exp + ak_admin) * profit_rate
        total_sum = ah_mat + ai_proc + aj_exp + ak_admin + al_profit
        
        # [요청 반영] 엑셀 수식 IF 적용: 발포업체는 내림, 나머지는 반올림
        final_p = excel_rounddown(total_sum, -1) if is_foam_company else excel_round(total_sum, -1)
        
        return pd.Series([mat_info['밀도'].values[0], mat_info['경도'].values[0], excel_round(af_qty, 2), int(ah_mat), int(ai_proc), int(final_p)], 
                         index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])

    if st.button("🚀 최종 단가 산출하기", use_container_width=True):
        st.session_state.last_result = pd.concat([edited_df, edited_df.apply(calculate_row, axis=1)], axis=1)

    if st.session_state.last_result is not None:
        st.subheader("📊 결과 리스트")
        st.dataframe(st.session_state.last_result, use_container_width=True)
        c_n, c_s, c_d = st.columns([3, 1, 1])
        with c_n: h_name = st.text_input("히스토리 명칭", value=datetime.now().strftime("%m%d_%H%M"), label_visibility="collapsed")
        with c_s: 
            if st.button("💾 히스토리에 저장", use_container_width=True): st.session_state.calc_history[h_name] = st.session_state.last_result
        with c_d: st.download_button("📥 CSV 저장", data=st.session_state.last_result.to_csv(index=False).encode('utf-8-sig'), file_name=f"{h_name}.csv", use_container_width=True)

# --- 4. 사이드바 히스토리 ---
st.sidebar.header("📁 계산 히스토리")
if st.session_state.calc_history:
    sel_h = st.sidebar.selectbox("내역 선택", list(st.session_state.calc_history.keys())[::-1])
    if st.sidebar.button("📂 불러오기"): st.session_state.last_result = st.session_state.calc_history[sel_h]
