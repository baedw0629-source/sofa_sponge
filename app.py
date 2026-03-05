import streamlit as st
import pandas as pd
import math
import json
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import io

# --- 1. 기본 설정 및 유틸리티 ---
st.set_page_config(page_title="스펀지 산출 및 DB 관리 TOOL", layout="wide")

# 숫자 화살표 제거 CSS
st.markdown("""
    <style>
    input[::-webkit-outer-spin-button], input[::-webkit-inner-spin-button] { -webkit-appearance: none; margin: 0; }
    input[type=number] { -moz-appearance: textfield; }
    button[data-testid="stNumberInputStepUp"], button[data-testid="stNumberInputStepDown"] { display: none; }
    </style>
    """, unsafe_allow_html=True)

def excel_round(number, decimals=0):
    if pd.isna(number): return 0
    multiplier = 10 ** decimals
    return int(Decimal(str(number * multiplier)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) / multiplier

# --- 2. 데이터 로드 및 상태 관리 ---
@st.cache_data
def fetch_raw_data():
    try:
        df = pd.read_csv('spongematerials.csv', encoding='utf-8-sig')
        df.columns = df.columns.str.strip().str.replace(' ', '')
        for col in ['가공업체단가', '발포업체단가']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', ''), errors='coerce').fillna(0.0)
        return df
    except:
        return pd.DataFrame(columns=['재질', '밀도', '경도', '가공업체단가', '발포업체단가'])

if "master_db" not in st.session_state:
    st.session_state.master_db = fetch_raw_data()

if "input_df" not in st.session_state:
    st.session_state.input_df = pd.DataFrame([{
        "선택업체": "진양", "재질": "선택하세요", "재단방식": "일반",
        "W(사선)": pd.NA, "W": pd.NA, "D": pd.NA, "T": pd.NA
    }])

if "last_result" not in st.session_state:
    st.session_state.last_result = None

# 히스토리 저장소
if "calc_history" not in st.session_state:
    st.session_state.calc_history = {}

# --- 3. 사이드바: 서버급 히스토리 관리 (Backup/Restore) ---
st.sidebar.header("📁 히스토리 마스터 관리")

# [핵심] 히스토리 전체를 파일로 백업
if st.session_state.calc_history:
    # 데이터프레임을 JSON으로 변환하여 저장
    history_to_save = {k: v.to_json() for k, v in st.session_state.calc_history.items()}
    json_str = json.dumps(history_to_save)
    st.sidebar.download_button(
        label="📥 전체 히스토리 백업 (파일 저장)",
        data=json_str,
        file_name=f"sponge_history_master_{datetime.now().strftime('%m%d')}.json",
        mime="application/json",
        help="이 파일을 가지고 있으면 언제든 과거 내역을 다시 불러올 수 있습니다."
    )

# [핵심] 백업된 파일로부터 히스토리 복구
uploaded_history = st.sidebar.file_uploader("📂 히스토리 복구 (파일 업로드)", type="json")
if uploaded_history:
    try:
        loaded_data = json.load(uploaded_history)
        # JSON을 다시 데이터프레임으로 복구
        st.session_state.calc_history = {k: pd.read_json(io.StringIO(v)) for k, v in loaded_data.items()}
        st.sidebar.success("✅ 히스토리가 성공적으로 복구되었습니다!")
    except:
        st.sidebar.error("❌ 유효한 히스토리 파일이 아닙니다.")

st.sidebar.write("---")
st.sidebar.subheader("📋 저장된 내역 리스트")
if st.session_state.calc_history:
    sel_h = st.sidebar.selectbox("불러올 내역 선택", list(st.session_state.calc_history.keys())[::-1])
    if st.sidebar.button("📂 데이터 불러오기"):
        st.session_state.last_result = st.session_state.calc_history[sel_h]
        st.sidebar.info(f"'{sel_h}' 내역을 화면에 띄웠습니다.")
    if st.sidebar.button("🗑️ 전체 삭제"):
        st.session_state.calc_history = {}
        st.rerun()
else:
    st.sidebar.info("저장된 내역이 없습니다.")

# --- 4. 메인 화면 탭 구성 (이후 로직은 동일) ---
tab1, tab2 = st.tabs(["🧽 단가 산출", "🗂️ 재질 DB 관리"])
# ... (이후 탭별 상세 로직 및 계산 엔진 코드는 이전과 동일하게 유지)
