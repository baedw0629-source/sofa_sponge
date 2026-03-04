import streamlit as st
import pandas as pd
import math

# --- 1. 기본 설정 및 데이터 로드 ---
st.set_page_config(page_title="스펀지 산출 TOOL", layout="wide")

# 숫자 입력창의 -, + 버튼을 숨기는 CSS
st.markdown("""
    <style>
    input[::-webkit-outer-spin-button],
    input[::-webkit-inner-spin-button] {
        -webkit-appearance: none;
        margin: 0;
    }
    input[type=number] {
        -moz-appearance: textfield;
    }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data
def load_data():
    try:
        # 사용자 지정 파일명 로드
        df = pd.read_csv('spongematerials.csv')
        return df
    except:
        return pd.DataFrame(columns=['재질', '밀도', '경도', '가공업체 단가', '발포업체 단가'])

sponge_db = load_data()

# --- 2. 사이드바: 기준 설정 (직접 입력) ---
st.sidebar.header("⚙️ 시스템 기준 설정")
h_cut_cost = st.sidebar.number_input("수평재단비 (원)", value=20.0, format="%.1f")
v_cut_cost = st.sidebar.number_input("수직재단비 (원)", value=11.0, format="%.1f")

loss_rate_val = st.sidebar.number_input("로스율 (%)", value=5.0, format="%.1f") / 100
admin_rate_val = st.sidebar.number_input("일반관리비율 (%)", value=5.0, format="%.1f") / 100
profit_rate_val = st.sidebar.number_input("이윤율 (%)", value=10.0, format="%.1f") / 100

# --- 3. 메인 화면: 일괄 입력 창 ---
st.title("🧽 스펀지 단가 산출 TOOL")

# 입력 필드 순서 및 명칭 변경 반영
if "input_df" not in st.session_state:
    st.session_state.input_df = pd.DataFrame(
        [{
            "선택업체": "진양",
            "재질": "재질을 선택하세요", 
            "재단방식": "일반", 
            "W
