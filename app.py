import streamlit as st
import pandas as pd
import math
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

# --- 1. 기본 설정 및 유틸리티 ---
st.set_page_config(page_title="스펀지 단가 산출 TOOL", layout="wide")

st.markdown("""
    <style>
    input[::-webkit-outer-spin-button], input[::-webkit-inner-spin-button] { -webkit-appearance: none; margin: 0; }
    input[type=number] { -moz-appearance: textfield; }
    button[data-testid="stNumberInputStepUp"], button[data-testid="stNumberInputStepDown"] { display: none; }
    </style>
    """, unsafe_allow_html=True)

# 엑셀 방식 사사오입 함수 (0.5에서 올림)
def excel_round(number, decimals=0):
    if pd.isna(number) or number is None: return 0
    multiplier = 10 ** decimals
    return float(Decimal(str(float(number) * multiplier)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) / multiplier

# 엑셀 방식 내림 함수
def excel_rounddown(number, decimals=0):
    if pd.isna(number) or number is None: return 0
    multiplier = 10 ** decimals
    return math.floor(float(number) * multiplier) / multiplier

# --- 2. 데이터 로드 로직 ---
@st.cache_data
def fetch_raw_data():
    encodings = ['utf-8-sig', 'cp949', 'euc-kr']
    for enc in encodings:
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

# [요청 반영] 수치 입력값은 빈칸(None)으로 시작
if "input_df" not in st.session_state:
    st.session_state.input_df = pd.DataFrame([{
        "선택업체": "진양", "재질": "선택하세요", "재단방식": "일반",
        "W(사선)": None, "W": None, "D": None, "T": None
    }])

if "last_result" not in st.session_state:
    st.session_state.last_result = None

if "calc_history" not in st.session_state:
    st.session_state.calc_history = {}

# --- 3. 상단 탭 구성 ---
tab1, tab2 = st.tabs(["🧽 단가 산출", "🗂️ 재질 DB 관리"])

with tab2:
    st.subheader("📋 마스터 재질 리스트 관리")
    edited_master = st.data_editor(st.session_state.master_db, num_rows="dynamic", use_container_width=True, key="master_db_editor")
    if st.button("💾 변경사항을 현재 계산기에 반영"):
        st.session_state.master_db = edited_master
        st.success("재질 정보가 업데이트되었습니다.")
    csv_master = edited_master.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 수정된 spongematerials.csv 다운로드", data=csv_master, file_name="spongematerials.csv")

with tab1:
    st.title("🧽 스펀지 단가 산출 TOOL")
    
    # 시스템 설정
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: h_cut = st.number_input("수평재단비(원)", value=21.0, format="%.1f")
    with c2: v_cut = st.number_input("수직재단비(원)", value=11.0, format="%.1f")
    with c3: loss_rate = st.number_input("로스율(%)", value=5.0, format="%.1f") / 100
    with c4: admin_rate = st.number_input("관리비(%)", value=5.0, format="%.1f") / 100
    with c5: profit_rate = st.number_input("이윤(%)", value=10.0, format="%.1f") / 100
    st.write("---")

    st.subheader("📝 목록 입력")
    material_list = ["선택하세요"] + sorted(st.session_state.master_db['재질'].dropna().unique().tolist())

    edited_df = st.data_editor(
        st.session_state.input_df,
        num_rows="dynamic",
        column_config={
            "선택업체": st.column_config.SelectboxColumn("선택업체", options=["진양", "폼웍스"], default="진양", required=False),
            "재질": st.column_config.SelectboxColumn("재질", options=material_list),
            "재단방식": st.column_config.SelectboxColumn("재단방식", options=["일반", "2D", "사선", "몰드"]),
            "W(사선)": st.column_config.NumberColumn("W(사선)", format="%d"),
            "W": st.column_config.NumberColumn("W", format="%d"),
            "D": st.column_config.NumberColumn("D", format="%d"),
            "T": st.column_config.NumberColumn("T", format="%d"),
        },
        use_container_width=True,
        key="main_editor"
    )

    # [오차 해결 핵심] 계산 엔진
    def calculate_row(row):
        if any(pd.isna(row[col]) or row[col] is None for col in ["W", "D", "T"]) or row['재질'] == "선택하세요":
            return pd.Series(["-", "-", 0, 0, 0, 0], index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])
        
        vol_unit = 918090 
        mat_info = st.session_state.master_db[st.session_state.master_db['재질'] == row['재질']]
        if mat_info.empty: return pd.Series(["미등록", "-", 0, 0, 0, 0], index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])

        # 업체 성격 정의
        is_jinyang = (row['선택업체'] == "진양") # 가공업체
        u_price = float(mat_info['가공업체단가' if is_jinyang else '발포업체단가'].values[0])
        ws, w, d, t = float(row['W(사선)']) if not pd.isna(row['W(사선)']) else 0.0, float(row['W']), float(row['D']), float(row['T'])

        # 1. 소요량(평) - 정밀도 유지
        af_qty_internal = (((ws + w) * d * t) / vol_unit) / 2 if row['재단방식'] == "사선" else (w * d * t) / vol_unit
        
        # 2. 재료비 (평수*단가 선 반올림 후 로스율 적용)
        ah_mat = excel_round(excel_round(af_qty_internal * u_price, 0) * (1.0 + loss_rate), 0)
        
        # 3. 가공비 (중간 반올림 없이 계산)
        ai_proc_raw = 0.0
        if row['재단방식'] == "2D": ai_proc_raw = ah_mat * 0.2
        elif is_jinyang:
            if row['재단방식'] == "일반": ai_proc_raw = (w/1000 * d/1000 * h_cut) + (w/1000 * d/1000 * t * v_cut)
            elif row['재단방식'] == "사선": ai_proc_raw = ((ws + w)/1000 * d/1000 * v_cut * t) + (w/1000 * d/1000 * h_cut)
        ai_proc = excel_round(ai_proc_raw, 0)

        # 4. 경비, 관리비, 이윤 (소수점 유지하며 합산 준비)
        aj_exp = ai_proc * 0.1
        ak_admin = (ah_mat + ai_proc + aj_exp) * admin_rate
        al_profit = (ai_proc + aj_exp + ak_admin) * profit_rate
        
        # 5. 최종 단가 (제공된 IF 수식 적용: 소수점 전체 합산 후 최종 반올림/내림)
        total_sum = ah_mat + ai_proc + aj_exp + ak_admin + al_profit
        
        # 진양은 가공업체이므로 ROUND 적용, 폼웍스는 발포업체로 가정하여 ROUNDDOWN 적용
        if is_jinyang:
            final_p = excel_round(total_sum, -1)
        else:
            final_p = excel_rounddown(total_sum, -1)
        
        return pd.Series([mat_info['밀도'].values[0], mat_info['경도'].values[0], excel_round(af_qty_internal, 2), int(ah_mat), int(ai_proc), int(final_p)], 
                         index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])

    st.divider()
    if st.button("🚀 최종 단가 산출하기"):
        results = edited_df.apply(calculate_row, axis=1)
        final_df = pd.concat([edited_df, results], axis=1)
        final_df = final_df[["선택업체", "재질", "밀도", "경도", "재단방식", "W(사선)", "W", "D", "T", "소요량(평)", "재료비", "가공비", "최종단가"]]
        final_df.index = range(1, len(final_df) + 1)
        st.session_state.last_result = final_df

    if st.session_state.last_result is not None:
        st.subheader("📊 결과 리스트")
        st.dataframe(st.session_state.last_result, use_container_width=True)
        st.write("") 
        
        # 버튼 수평 정렬
        col_name, col_hist, col_csv = st.columns([3, 1, 1])
        with col_name:
            hist_name = st.text_input("저장할 히스토리 명칭", value=datetime.now().strftime("%m%d_%H%M"), label_visibility="collapsed", placeholder="히스토리 명칭 입력")
        with col_hist:
            if st.button("💾 히스토리에 저장", use_container_width=True):
                st.session_state.calc_history[hist_name] = st.session_state.last_result
                st.success(f"'{hist_name}' 저장 완료")
        with col_csv:
            csv_res = st.session_state.last_result.to_csv(index=True, index_label="No").encode('utf-8-sig')
            st.download_button("📥 결과 CSV 저장", data=csv_res, file_name=f"{hist_name}.csv", use_container_width=True)

# --- 4. 사이드바 히스토리 ---
st.sidebar.header("📁 계산 히스토리")
if st.session_state.calc_history:
    sel_h = st.sidebar.selectbox("내역 선택", list(st.session_state.calc_history.keys())[::-1])
    if st.sidebar.button("📂 불러오기"):
        st.session_state.last_result = st.session_state.calc_history[sel_h]
        st.sidebar.success(f"'{sel_h}' 로드 완료")
    if st.sidebar.button("🗑️ 전체 삭제"):
        st.session_state.calc_history = {}
        st.rerun()
else:
    st.sidebar.info("저장된 내역이 없습니다.")
