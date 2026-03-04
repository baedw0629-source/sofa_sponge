import streamlit as st
import pandas as pd
import math
import io

# --- 1. 기본 설정 ---
st.set_page_config(page_title="스펀지 산출 TOOL", layout="wide")

# 숫자 입력창 화살표 제거 CSS
st.markdown("""
    <style>
    input[::-webkit-outer-spin-button],
    input[::-webkit-inner-spin-button] { -webkit-appearance: none; margin: 0; }
    input[type=number] { -moz-appearance: textfield; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data
def load_data():
    try:
        # 파일명 확인
        df = pd.read_csv('spongematerials.csv', encoding='utf-8-sig')
        # 모든 컬럼명에서 공백 제거 (KeyError 방지)
        df.columns = df.columns.str.strip().str.replace(' ', '')
        
        # 단가 데이터에서 콤마(,) 등 제거 후 숫자로 강제 변환 (TypeError 방지)
        for col in ['가공업체단가', '발포업체단가']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '').str.replace('원', '').str.strip()
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return pd.DataFrame()

if st.sidebar.button("♻️ 데이터 새로고침"):
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

material_list = ["선택하세요"] + sponge_db['재질'].unique().tolist() if not sponge_db.empty else ["파일 확인 필요"]

edited_df = st.data_editor(
    st.session_state.input_df,
    num_rows="dynamic",
    column_config={
        "선택업체": st.column_config.SelectboxColumn("선택업체", options=["진양", "폼웍스"]),
        "재질": st.column_config.SelectboxColumn("재질", options=material_list),
        "재단방식": st.column_config.SelectboxColumn("재단방식", options=["일반", "2D", "사선", "몰드"]),
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

    # 업체별 단가 선택 (공백 제거된 컬럼명 사용)
    is_jinyang = row['선택업체'] == "진양"
    u_price = float(material_info['가공업체단가'].values[0]) if is_jinyang else float(material_info['발포업체단가'].values[0])
    calc_mode = "가공업체" if is_jinyang else "발포업체"

    # 소요량 및 재료비 계산
    w_saseon, w, d, t = float(row['W(사선)']), float(row['W']), float(row['D']), float(row['T'])
    af_qty = (((w_saseon + w) * d * t) / vol_unit) / 2 if row['재단방식'] == "사선" else (w * d * t) / vol_unit
    ah_mat_cost = af_qty * u_price if calc_mode == "발포업체" else af_qty * (1.0 + loss_rate_val) * u_price

    # 가공비
    ai_proc_cost = 0.0
    if row['재단방식'] == "2D":
        ai_proc_cost = ah_mat_cost * 0.2
    elif calc_mode != "발포업체":
        if row['재단방식'] == "일반":
            ai_proc_cost = (w/1000 * d/1000 * h_cut_cost) + (w/1000 * d/1000 * t * v_cut_cost)
        elif row['재단방식'] == "사선":
            ai_proc_cost = ((w_saseon + w)/1000 * d/1000 * v_cut_cost * t) + (w/1000 * d/1000 * h_cut_cost)

    # 기타 비용 및 최종 단가
    aj_exp = ai_proc_cost * 0.1
    ak_admin = 0.0 if calc_mode == "발포업체" else (ah_mat_cost + ai_proc_cost + aj_exp) * admin_rate_val
    al_profit = (ai_proc_cost + aj_exp + ak_admin) * profit_rate_val
    total = ah_mat_cost + ai_proc_cost + aj_exp + ak_admin + al_profit
    am_price = math.floor(total / 10) * 10 if calc_mode == "발포업체" else round(total / 10) * 10
    
    density = material_info['밀도'].values[0] if '밀도' in material_info.columns else "-"
    hardness = material_info['경도'].values[0] if '경도' in material_info.columns else "-"

    return pd.Series([density, hardness, round(af_qty, 3), round(ah_mat_cost), round(ai_proc_cost), am_price], 
                     index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])

# --- 5. 결과 출력 ---
st.divider()
if st.button("🚀 최종 단가 산출하기"):
    if not edited_df.empty:
        results = edited_df.apply(calculate_row, axis=1)
        final_df = pd.concat([edited_df, results], axis=1)
        
        # 순서 재배치 및 인덱스 조정
        final_df = final_df[["선택업체", "재질", "밀도", "경도", "재단방식", "W(사선)", "W", "D", "T", "소요량(평)", "재료비", "가공비", "최종단가"]]
        final_df.index = range(1, len(final_df) + 1)
        
        st.subheader("📊 산출 결과 리스트")
        st.dataframe(final_df, use_container_width=True)
        
        # 엑셀 다운로드 (openpyxl 필요)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            final_df.to_excel(writer, index=True, index_label="No", sheet_name='Result')
        
        st.download_button(
            label="📥 결과 저장(Excel)",
            data=output.getvalue(),
            file_name="sponge_calc_result.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
