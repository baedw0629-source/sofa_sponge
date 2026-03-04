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
            "W(사선)": 0.0,
            "W": 500.0, 
            "D": 400.0, 
            "T": 300.0
        }]
    )

material_list = sponge_db['재질'].unique().tolist() if not sponge_db.empty else ["수동입력"]

st.subheader("📝 산출 목록 입력")
edited_df = st.data_editor(
    st.session_state.input_df,
    num_rows="dynamic",
    column_config={
        "선택업체": st.column_config.SelectboxColumn("선택업체", options=["진양", "폼웍스"], width="small"),
        "재질": st.column_config.SelectboxColumn("재질", options=material_list, width="medium"),
        "재단방식": st.column_config.SelectboxColumn("재단방식", options=["일반", "2D", "사선", "몰드"]),
        "W(사선)": st.column_config.NumberColumn("W(사선)", format="%.0f", help="사선 재단 시에만 입력"),
        "W": st.column_config.NumberColumn("W", format="%.0f"),
        "D": st.column_config.NumberColumn("D", format="%.0f"),
        "T": st.column_config.NumberColumn("T", format="%.0f"),
    },
    use_container_width=True,
    key="editor"
)

# --- 4. 계산 엔진 ---
def calculate_row(row):
    vol_unit = 303 * 303 * 10
    material_info = sponge_db[sponge_db['재질'] == row['재질']]
    
    if material_info.empty:
        return pd.Series(["-", "-", 0, 0, 0, 0], index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])

    density = material_info['밀도'].values[0]
    hardness = material_info['경도'].values[0]
    
    # 업체별 단가 선택 로직
    if row['선택업체'] == "진양":
        u_price = material_info['가공업체 단가'].values[0]
        calc_mode = "가공업체"
    else:
        u_price = material_info['발포업체 단가'].values[0]
        calc_mode = "발포업체"

    # 1. 소요량(AF) - 변경된 변수명 적용
    if row['재단방식'] == "사선":
        af_qty = (((row['W(사선)'] + row['W']) * row['D'] * row['T']) / vol_unit) / 2
    else:
        af_qty = (row['W'] * row['D'] * row['T']) / vol_unit

    # 2. 재료비(AH)
    ah_mat_cost = af_qty * u_price if calc_mode == "발포업체" else af_qty * (1 + loss_rate_val) * u_price

    # 3. 가공비(AI)
    ai_proc_cost = 0
    if row['재단방식'] == "2D":
        ai_proc_cost = ah_mat_cost * 0.2
    elif calc_mode != "발포업체":
        if row['재단방식'] == "일반":
            ai_proc_cost = (row['W']/1000 * row['D']/1000 * h_cut_cost) + (row['W']/1000 * row['D']/1000 * row['T'] * v_cut_cost)
        elif row['재단방식'] == "사선":
            ai_proc_cost = ((row['W(사선)']+row['W'])/1000 * row['D']/1000 * v_cut_cost * row['T']) + (row['W']/1000 * row['D']/1000 * h_cut_cost)

    # 4. 경비, 관리비, 이윤
    aj_exp = ai_proc_cost * 0.1
    ak_admin = 0 if calc_mode == "발포업체" else (ah_mat_cost + ai_proc_cost + aj_exp) * admin_rate_val
    al_profit = (ai_proc_cost + aj_exp + ak_admin) * profit_rate_val

    # 5. 최종 단가(AM)
    total = ah_mat_cost + ai_proc_cost + aj_exp + ak_admin + al_profit
    am_price = math.floor(total / 10) * 10 if calc_mode == "발포업체" else round(total / 10) * 10
    
    return pd.Series([density, hardness, round(af_qty, 3), round(ah_mat_cost), round(ai_proc_cost), am_price], 
                     index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])

# --- 5. 결과 출력 ---
if st.button("🚀 전체 단가 계산"):
    results = edited_df.apply(calculate_row, axis=1)
    final_df = pd.concat([edited_df, results], axis=1)
    
    st.divider()
    st.subheader("📊 산출 결과 리스트")
    st.dataframe(final_df, use_container_width=True)
    
    csv = final_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 결과 CSV 다운로드", data=csv, file_name="sponge_calc_results.csv", mime="text/csv")
