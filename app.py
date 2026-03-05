import streamlit as st
import pandas as pd
import math
from datetime import datetime

# --- 1. 기본 설정 및 데이터 로드 ---
st.set_page_config(page_title="스펀지 단가 산출 TOOL", layout="wide")

# 숫자 입력창 화살표 제거 CSS
st.markdown("""
    <style>
    input[::-webkit-outer-spin-button], input[::-webkit-inner-spin-button] { -webkit-appearance: none; margin: 0; }
    input[type=number] { -moz-appearance: textfield; }
    button[data-testid="stNumberInputStepUp"], button[data-testid="stNumberInputStepDown"] { display: none; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data
def load_data():
    try:
        df = pd.read_csv('spongematerials.csv', encoding='utf-8-sig')
        df.columns = df.columns.str.strip().str.replace(' ', '')
        for col in ['가공업체단가', '발포업체단가']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', ''), errors='coerce').fillna(0.0)
        return df
    except:
        return pd.DataFrame()

sponge_db = load_data()

# --- 2. 상태(Session State) 초기화 ---
if "input_df" not in st.session_state:
    # 1번 요청 반영: 수치 입력값을 None으로 설정하여 빈칸으로 시작
    st.session_state.input_df = pd.DataFrame([{
        "선택업체": "진양", 
        "재질": "선택하세요", 
        "재단방식": "일반",
        "W(사선)": None, 
        "W": None, 
        "D": None, 
        "T": None
    }])

if "last_result" not in st.session_state:
    st.session_state.last_result = None

if "calc_history" not in st.session_state:
    st.session_state.calc_history = {}

# --- 3. 상단 제목 및 시스템 설정 (가로 배치) ---
st.title("🧽 스펀지 단가 산출 TOOL")

st.write("---")
st.subheader("⚙️ 시스템 기준 설정")
c1, c2, c3, c4, c5 = st.columns(5)
with c1: h_cut = st.number_input("수평재단비(원)", value=20.0, format="%.1f")
with c2: v_cut = st.number_input("수직재단비(원)", value=11.0, format="%.1f")
with c3: loss_rate = st.number_input("로스율(%)", value=5.0, format="%.1f") / 100
with c4: admin_rate = st.number_input("관리비(%)", value=5.0, format="%.1f") / 100
with c5: profit_rate = st.number_input("이윤(%)", value=10.0, format="%.1f") / 100
st.write("---")

# --- 4. 메인 입력창 (2번 요청 반영) ---
st.subheader("📝 산출 목록 입력")
material_list = ["선택하세요"] + (sorted(sponge_db['재질'].unique().tolist()) if not sponge_db.empty else [])

# 2번 요청 반영: SelectboxColumn에 default="진양" 설정
edited_df = st.data_editor(
    st.session_state.input_df,
    num_rows="dynamic",
    column_config={
        "선택업체": st.column_config.SelectboxColumn(
            "선택업체", 
            options=["진양", "폼웍스"], 
            required=True,
            default="진양"  # 행 추가 시 기본값 고정
        ),
        "재질": st.column_config.SelectboxColumn("재질", options=material_list),
        "재단방식": st.column_config.SelectboxColumn("재단방식", options=["일반", "2D", "사선", "몰드"]),
        "W(사선)": st.column_config.NumberColumn("W(사선)", format="%.0f"),
        "W": st.column_config.NumberColumn("W", format="%.0f"),
        "D": st.column_config.NumberColumn("D", format="%.0f"),
        "T": st.column_config.NumberColumn("T", format="%.0f"),
    },
    use_container_width=True,
    key="main_editor"
)

# --- 5. 계산 엔진 (None 값 예외 처리 추가) ---
def calculate_row(row):
    # 필수 입력값(W, D, T) 중 하나라도 비어있으면 계산 스킵
    if any(pd.isna(row[col]) for col in ["W", "D", "T"]) or row['재질'] == "선택하세요":
        return pd.Series(["-", "-", 0, 0, 0, 0], index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])
    
    vol_unit = 303 * 303 * 10
    mat_info = sponge_db[sponge_db['재질'] == row['재질']]
    if mat_info.empty:
        return pd.Series(["미등록", "-", 0, 0, 0, 0], index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])

    is_jinyang = (row['선택업체'] == "진양")
    u_price = float(mat_info['가공업체단가' if is_jinyang else '발포업체단가'].values[0])
    
    # None 값을 0으로 안전하게 치환하여 계산
    ws = float(row['W(사선)']) if not pd.isna(row['W(사선)']) else 0.0
    w, d, t = float(row['W']), float(row['D']), float(row['T'])

    af_qty = (((ws + w) * d * t) / vol_unit) / 2 if row['재단방식'] == "사선" else (w * d * t) / vol_unit
    ah_mat = af_qty * u_price if not is_jinyang else af_qty * (1.0 + loss_rate) * u_price
    
    ai_proc = 0.0
    if row['재단방식'] == "2D":
        ai_proc = ah_mat * 0.2
    elif is_jinyang:
        if row['재단방식'] == "일반":
            ai_proc = (w/1000 * d/1000 * h_cut) + (w/1000 * d/1000 * t * v_cut)
        elif row['재단방식'] == "사선":
            ai_proc = ((ws + w)/1000 * d/1000 * v_cut * t) + (w/1000 * d/1000 * h_cut)

    total = (ah_mat + ai_proc + (ai_proc * 0.1)) * (1.0 + admin_rate) * (1.0 + profit_rate)
    final_p = math.floor(total/10)*10 if not is_jinyang else round(total/10)*10
    
    return pd.Series([
        mat_info['밀도'].values[0], 
        mat_info['경도'].values[0], 
        round(af_qty, 3), 
        round(ah_mat), 
        round(ai_proc), 
        final_p
    ], index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])

# --- 6. 결과 출력 및 다운로드 (3번 요청 반영: 상태 유지) ---
st.divider()
if st.button("🚀 최종 단가 산출하기"):
    results = edited_df.apply(calculate_row, axis=1)
    final_df = pd.concat([edited_df, results], axis=1)
    final_df = final_df[["선택업체", "재질", "밀도", "경도", "재단방식", "W(사선)", "W", "D", "T", "소요량(평)", "재료비", "가공비", "최종단가"]]
    final_df.index = range(1, len(final_df) + 1)
    st.session_state.last_result = final_df

if st.session_state.last_result is not None:
    st.subheader("📊 산출 결과 리스트")
    st.dataframe(st.session_state.last_result, use_container_width=True)
    
    col_save, col_down = st.columns([1, 4])
    with col_save:
        if st.button("💾 이 내역 히스토리에 저장"):
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.session_state.calc_history[now] = st.session_state.last_result
            st.success(f"저장 완료: {now}")
    with col_down:
        csv = st.session_state.last_result.to_csv(index=True, index_label="No").encode('utf-8-sig')
        st.download_button("📥 결과 저장(CSV)", data=csv, file_name=f"sponge_result_{datetime.now().strftime('%m%d_%H%M')}.csv")

# --- 7. 사이드바: 히스토리 관리 (4번 요청 반영) ---
st.sidebar.header("📁 계산 히스토리")
if st.session_state.calc_history:
    selected_hist = st.sidebar.selectbox("저장된 내역 선택", list(st.session_state.calc_history.keys())[::-1])
    if st.sidebar.button("📂 불러오기"):
        st.session_state.last_result = st.session_state.calc_history[selected_hist]
        st.sidebar.success("내역을 불러왔습니다.")
    if st.sidebar.button("🗑️ 히스토리 전체 삭제"):
        st.session_state.calc_history = {}
        st.rerun()
else:
    st.sidebar.info("저장된 히스토리가 없습니다.")

st.sidebar.write("---")
if st.sidebar.button("♻️ 데이터 강제 새로고침"):
    st.cache_data.clear()
    st.rerun()
