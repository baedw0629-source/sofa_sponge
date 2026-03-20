import streamlit as st
import pandas as pd
import math
import base64
import requests
import io # 엑셀 생성을 위해 필수
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

# --- 1. 기본 설정 및 유틸리티 ---
st.set_page_config(page_title="스펀지 산출 TOOL", layout="wide")

st.markdown("""
    <style>
    input[::-webkit-outer-spin-button], input[::-webkit-inner-spin-button] { -webkit-appearance: none; margin: 0; }
    input[type=number] { -moz-appearance: textfield; }
    button[data-testid="stNumberInputStepUp"], button[data-testid="stNumberInputStepDown"] { display: none; }
    </style>
    """, unsafe_allow_html=True)

# 엑셀 방식 반올림/내림 함수
def excel_round(number, decimals=0):
    if pd.isna(number) or number is None: return 0
    multiplier = 10 ** decimals
    return float(Decimal(str(float(number) * multiplier)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) / multiplier

def excel_rounddown(number, decimals=0):
    if pd.isna(number) or number is None: return 0
    multiplier = 10 ** decimals
    return math.floor(float(number) * multiplier) / multiplier

# GitHub API 업데이트 함수
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

# --- 2. 데이터 로드 (버전 관리 대응) ---
@st.cache_data
def fetch_raw_data():
    for enc in ['utf-8-sig', 'cp949', 'euc-kr']:
        try:
            df = pd.read_csv('spongematerials.csv', encoding=enc)
            df.columns = df.columns.str.strip().str.replace(' ', '')
            if '버전' not in df.columns: df.insert(0, '버전', '기본')
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

# [Tab 2: DB 관리]
with tab2:
    st.subheader("📋 재질 DB")
    # 한 박스 안에 깔끔하게 안내 문구 통합
    st.info("""
    ✅ 단가가 변경되는 경우, 행을 추가하여 신규 버전 및 단가 내용을 입력하세요.
    
    📌 **히스토리**
    - 25.09: 진양 통합으로 인한 단가 인하
    - 23.11: 제3유에프 단가 산정 시 사용
    """)
    
    edited_master = st.data_editor(st.session_state.master_db, num_rows="dynamic", use_container_width=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🚀 현재 계산기에 즉시 반영 (임시)", use_container_width=True):
            st.session_state.master_db = edited_master
            st.success("반영되었습니다.")
    with c2:
        if st.button("🌐 DB 저장", use_container_width=True):
            if update_github_file(edited_master.to_csv(index=False)):
                st.success("GitHub 업데이트 성공!"); st.cache_data.clear()
            else: st.error("GitHub 업데이트 실패. Secrets를 확인하세요.")

# [Tab 1: 단가 산출]
with tab1:
    st.title("🧽 스펀지 단가 산출 TOOL")
    
    # 버전 선택 UI
    v_list = sorted(st.session_state.master_db['버전'].unique().tolist())
    sel_ver = st.selectbox("📌 적용할 단가 버전 선택", v_list, index=len(v_list)-1)
    db_ver = st.session_state.master_db[st.session_state.master_db['버전'] == sel_ver]
    
    col_sys = st.columns(5)
    h_cut = col_sys[0].number_input("수평재단비", value=21.0, format="%.1f")
    v_cut = col_sys[1].number_input("수직재단비", value=11.0, format
