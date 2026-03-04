import streamlit as st
import pandas as pd
import math

# --- 1. 기본 설정 및 데이터 로드 ---
st.set_page_config(page_title="스펀지 일괄 단가 산출기", layout="wide")

@st.cache_data
def load_data():
    try:
        # 6,000개 자재 데이터 로드
        df = pd.read_csv('materials.csv')
        return df[df['규격구분'].str.contains('스펀지', na=False)]
    except:
        return pd.DataFrame(columns=['자재코드', '자재명', '주거래단가'])

sponge_db = load_data()

# --- 2. 사이드바: 시스템 기준 설정 ---
st.sidebar.header("⚙️ 시스템 기준 설정")
# 요청하신 대로 명칭 변경
h_cut_cost = st.sidebar.number_input("수평재단비)", value=20.0)
v_cut_cost = st.sidebar.number_input("수직재단비)", value=11.0)

loss_rate = st.sidebar.slider("기본 로스율 (%)", 0, 20, 5) / 100
admin_rate = st.sidebar.slider("일반관리비율 (%)", 0, 10, 5) / 100
profit_rate = st.sidebar.slider("이윤율 (%)", 0, 20, 10) / 100

# --- 3. 메인 화면 ---
st.title("🧽 스펀지 일괄 단가 산출 툴")
st.caption("엑셀처럼 여러 줄을 입력하여 한 번에 단가를 산출할 수 있습니다.")

# 입력 데이터프레임 초기화
if "input_df" not in st.session_state:
    st.session_state.input_df = pd.DataFrame(
        [{
            "재질명": "재질을 선택하세요", 
            "재단방식": "일반", 
            "업체구분": "가공업체", 
            "W(O)": 500.0, "D(P)": 400.0, "T(Q)": 300.0, "N(사선)": 0.0, 
            "평단가": 275.0
        }]
    )

# --- 4. 엑셀형 데이터 에디터 ---
st.subheader("📝 산출 목록 입력")
# 재질명 리스트 준비
material_list = sponge_db['자재명'].unique().tolist() if not sponge_db.empty else ["수동입력"]

edited_df = st.data_editor(
    st.session_state.input_df,
    num_rows="dynamic", # 줄 추가/삭제 가능
    column_config={
        "재질명": st.column_config.SelectboxColumn("재질명", options=material_list, width="medium"),
        "재단방식": st.column_config.SelectboxColumn("재단방식", options=["일반", "2D", "사선", "몰드"]),
        "업체구분": st.column_config.SelectboxColumn("업체구분", options=["가공업체", "발포업체"]),
    },
    use_container_width=True,
    key="editor"
)

# --- 5. 계산 엔진 함수 ---
def calculate_row(row):
    vol_unit = 303 * 303 * 10
    
    # 평단가 자동 매칭 (DB에 있을 경우)
    u_price = row['평단가']
    if not sponge_db.empty and row['재질명'] in sponge_db['자재명'].values:
        u_price = sponge_db[sponge_db['자재명'] == row['재질명']]['주거래단가'].values[0]

    # AF: 소요량
    if row['재단방식'] == "사선":
        af_qty = (((row['N(사선)'] + row['W(O)']) * row['D(P)'] * row['T(Q)']) / vol_unit) / 2
    else:
        af_qty = (row['W(O)'] * row['D(P)'] * row['T(Q)']) / vol_unit

    # AH: 재료비
    ah_mat_cost = af_qty * u_price if row['업체구분'] == "발포업체" else af_qty * (1 + loss_rate) * u_price

    # AI: 가공비 (명칭 변경 반영)
    ai_proc_cost = 0
    if row['재단방식'] == "2D":
        ai_proc_cost = ah_mat_cost * 0.2
    elif row['업체구분'] != "발포업체":
        if row['재단방식'] == "일반":
            # 수평재단비(h_cut_cost) + 수직재단비(v_cut_cost) 로직
            ai_proc_cost = (row['W(O)']/1000 * row['D(P)']/1000 * h_cut_cost) + (row['W(O)']/1000 * row['D(P)']/1000 * row['T(Q)'] * v_cut_cost)
        elif row['재단방식'] == "사선":
            ai_proc_cost = ((row['N(사선)']+row['W(O)'])/1000 * row['D(P)']/1000 * v_cut_cost * row['T(Q)']) + (row['W(O)']/1000 * row['D(P)']/1000 * h_cut_cost)

    # AJ, AK, AL: 경비, 관리비, 이윤
    aj_exp = ai_proc_cost * 0.1
    ak_admin = 0 if row['업체구분'] == "발포업체" else (ah_mat_cost + ai_proc_cost + aj_exp) * admin_rate
    al_profit = (ai_proc_cost + aj_exp + ak_admin) * profit_rate

    # AM: 최종 단가
    total = ah_mat_cost + ai_proc_cost + aj_exp + ak_admin + al_profit
    am_price = math.floor(total / 10) * 10 if row['업체구분'] == "발포업체" else round(total / 10) * 10
    
    return pd.Series([round(af_qty, 2), round(am_price)], index=["소요량(평)", "최종단가(원)"])

# --- 6. 결과 출력 및 다운로드 ---
if st.button("🚀 전체 단가 계산하기"):
    results = edited_df.apply(calculate_row, axis=1)
    final_df = pd.concat([edited_df, results], axis=1)
    
    st.divider()
    st.subheader("📊 산출 결과")
    st.dataframe(final_df, use_container_width=True)
    
    # 엑셀/CSV로 결과 내보내기
    csv = final_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 계산 결과 다운로드 (CSV)", data=csv, file_name="sponge_costs.csv", mime="text/csv")

