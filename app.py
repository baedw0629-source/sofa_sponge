import streamlit as st
import pandas as pd
import math

st.set_page_config(page_title="스펀지 산출 TOOL", layout="wide")

# 숫자 입력창 화살표 제거 CSS
st.markdown("""
    <style>
    input[::-webkit-outer-spin-button],
    input[::-webkit-inner-spin-button] { -webkit-appearance: none; margin: 0; }
    input[type=number] { -moz-appearance: textfield; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. 데이터 로드 및 정제 ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv('spongematerials.csv', encoding='utf-8-sig')
        # 컬럼명에서 모든 공백 제거
        df.columns = df.columns.str.strip().str.replace(' ', '')
        
        # [중요] 단가 컬럼에서 숫자 외 문자(콤마, 원 등) 제거 후 숫자로 변환
        for col in ['가공업체단가', '발포업체단가']:
            if col in df.columns:
                # 문자열인 경우에만 정제 작업 수행
                df[col] = df[col].astype(str).str.replace(',', '').str.replace('원', '').str.strip()
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # 밀도, 경도도 문자열로 안전하게 처리
        if '밀도' in df.columns: df['밀도'] = df['밀도'].astype(str)
        if '경도' in df.columns: df['경도'] = df['경도'].astype(str)
            
        return df
    except Exception as e:
        st.error(f"파일 로드 중 오류 발생: {e}")
        return pd.DataFrame()

if st.sidebar.button("♻️ 데이터 새로고침 (캐시 비우기)"):
    st.cache_data.clear()
    st.rerun()

sponge_db = load_data()

# --- 2. 시스템 기준 설정 ---
st.sidebar.header("⚙️ 시스템 기준 설정")
h_cut_cost = st.sidebar.number_input("수평재단비 (원)", value=20.0, format="%.1f")
v_cut_cost = st.sidebar.number_input("수직재단비 (원)", value=11.0, format="%.1f")
loss_rate_val = st.sidebar.number_input("로스율 (%)", value=5.0, format="%.1f") / 100
admin_rate_val = st.sidebar.number_input("일반관리비율 (%)", value=5.0, format="%.1f") / 100
profit_rate_val = st.sidebar.number_input("이윤율 (%)", value=10.0, format="%.1f") / 100

# --- 3. 입력 창 ---
st.title("🧽 스펀지 단가 산출 TOOL")

if "input_df" not in st.session_state:
    st.session_state.input_df = pd.DataFrame([{
        "선택업체": "진양", "재질": "선택하세요", "재단방식": "일반",
        "W(사선)": 0.0, "W": 500.0, "D": 400.0, "T": 300.0
    }])

material_list = ["선택하세요"] + sponge_db['재질'].unique().tolist() if not sponge_db.empty else ["데이터 없음"]

edited_df = st.data_editor(
    st.session_state.input_df,
    num_rows="dynamic",
    column_config={
        "선택업체": st.column_config.SelectboxColumn("선택업체", options=["진양", "폼웍스"]),
        "재질": st.column_config.SelectboxColumn("재질", options=material_list),
        "재단방식": st.column_config.SelectboxColumn("재단방식", options=["일반", "2D", "사선", "몰드"]),
        "W(사선)": st.column_config.NumberColumn("W(사선)", format="%.0f"),
        "W": st.column_config.NumberColumn("W", format="%.0f"),
        "D": st.column_config.NumberColumn("D", format="%.0f"),
        "T": st.column_config.NumberColumn("T", format="%.0f"),
    },
    use_container_width=True,
    key="editor"
)

# --- 4. 계산 엔진 ---
def calculate_row(row):
    if row['재질'] == "선택하세요":
        return pd.Series(["-", "-", 0, 0, 0, 0], index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])
    
    vol_unit = 303 * 303 * 10
    material_info = sponge_db[sponge_db['재질'] == row['재질']]
    
    if material_info.empty:
        return pd.Series(["미등록", "-", 0, 0, 0, 0], index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])

    # 업체 선택에 따른 단가 로드 (가공업체단가 / 발포업체단가)
    try:
        if row['선택업체'] == "진양":
            u_price = float(material_info['가공업체단가'].values[0])
            calc_mode = "가공업체"
        else:
            u_price = float(material_info['발포업체단가'].values[0])
            calc_mode = "발포업체"
    except Exception:
        u_price = 0.0
        calc_mode = "오류"

    # 1. 소요량(AF)
    af_qty = (((row['W(사선)'] + row['W']) * row['D'] * row['T']) / vol_unit) / 2 if row['재단방식'] == "사선" else (row['W'] * row['D'] * row['T']) / vol_unit

    # 2. 재료비(AH) - 모든 변수를 float으로 강제 형변환하여 TypeError 방지
    ah_mat_cost = float(af_qty) * u_price if calc_mode == "발포업체" else float(af_qty) * (1.0 + float(loss_rate_val)) * u_price

    # 3. 가공비(AI)
    ai_proc_cost = 0.0
    if row['재단방식'] == "2D":
        ai_proc_cost = ah_mat_cost * 0.2
    elif calc_mode != "발포업체":
        w, d, t, n = float(row['W']), float(row['D']), float(row['T']), float(row['W(사선)'])
        if row['재단방식'] == "일반":
            ai_proc_cost = (w/1000 * d/1000 * h_cut_cost) + (w/1000 * d/1000 * t * v_cut_cost)
        elif row['재단방식'] == "사선":
            ai_proc_cost = ((n+w)/1000 * d/1000 * v_cut_cost * t) + (w/1000 * d/1000 * h_cut_cost)

    # 4. 경비, 관리비, 이윤
    aj_exp = ai_proc_cost * 0.1
    ak_admin = 0.0 if calc_mode == "발포업체" else (ah_mat_cost + ai_proc_cost + aj_exp) * admin_rate_val
    al_profit = (ai_proc_cost + aj_exp + ak_admin) * profit_rate_val

    # 5. 최종 단가(AM)
    total = ah_mat_cost + ai_proc_cost + aj_exp + ak_admin + al_profit
    am_price = math.floor(total / 10) * 10 if calc_mode == "발포업체" else round(total / 10) * 10
    
    return pd.Series([material_info['밀도'].values[0], material_info['경도'].values[0], 
                     round(af_qty, 3), round(ah_mat_cost), round(ai_proc_cost), am_price], 
                     index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])

# --- 5. 실행 결과 ---
if st.button("🚀 전체 단가 계산"):
    if not sponge_db.empty:
        results = edited_df.apply(calculate_row, axis=1)
        final_df = pd.concat([edited_df, results], axis=1)
        st.divider()
        st.dataframe(final_df, use_container_width=True)
        st.download_button("📥 결과 저장(CSV)", data=final_df.to_csv(index=False).encode('utf-8-sig'), file_name="sponge_result.csv")
    else:
        st.error("데이터 파일이 로드되지 않았습니다.")
