import streamlit as st
import pandas as pd
import math

# --- 1. 기본 설정 및 보안 로드 ---
st.set_page_config(page_title="스펀지 산출 TOOL", layout="wide")

# 숫자 입력창 화살표 제거 CSS
st.markdown("""
    <style>
    input[::-webkit-outer-spin-button], input[::-webkit-inner-spin-button] { -webkit-appearance: none; margin: 0; }
    input[type=number] { -moz-appearance: textfield; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data
def load_data():
    try:
        # 파일 읽기 (utf-8-sig로 엑셀 특유의 한글 깨짐 방지)
        df = pd.read_csv('sofa_sponge/spongematerials.csv', encoding='utf-8-sig')
        
        # [중요] 컬럼명 청소: 모든 공백을 제거하여 '가공업체 단가'와 '가공업체단가'를 똑같이 취급합니다.
        df.columns = df.columns.str.strip().str.replace(' ', '').str.replace('\t', '')
        
        # [중요] 단가 데이터 정제: 콤마(,), '원', 공백을 제거하고 강제로 숫자로 바꿉니다.
        for col in ['가공업체단가', '발포업체단가']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '').str.replace('원', '').str.strip()
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        
        return df
    except Exception as e:
        st.error(f"⚠️ 파일 로드 중 오류 발생: {e}")
        return pd.DataFrame()

# 데이터 새로고침
if st.sidebar.button("♻️ 데이터 강제 새로고침"):
    st.cache_data.clear()
    st.rerun()

sponge_db = load_data()

# --- 2. 시스템 기준 설정 ---
st.sidebar.header("⚙️ 시스템 설정")
h_cut = st.sidebar.number_input("수평재단비", value=20.0)
v_cut = st.sidebar.number_input("수직재단비", value=11.0)
loss_rate = st.sidebar.number_input("로스율(%)", value=5.0) / 100
admin_rate = st.sidebar.number_input("관리비(%)", value=5.0) / 100
profit_rate = st.sidebar.number_input("이윤(%)", value=10.0) / 100

# --- 3. 입력 창 ---
st.title("🧽 스펀지 단가 산출 TOOL")

if "input_df" not in st.session_state:
    st.session_state.input_df = pd.DataFrame([{
        "선택업체": "진양", "재질": "선택하세요", "재단방식": "일반",
        "W(사선)": 0.0, "W": 500.0, "D": 400.0, "T": 300.0
    }])

material_list = ["선택하세요"]
if not sponge_db.empty:
    material_list += sorted(sponge_db['재질'].unique().tolist())

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

# --- 4. 계산 엔진 (모든 에러를 방어하도록 설계) ---
def calculate_row(row):
    if row['재질'] == "선택하세요" or row['재질'] == "":
        return pd.Series(["-", "-", 0, 0, 0, 0], index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])
    
    try:
        vol_unit = 303 * 303 * 10
        material_info = sponge_db[sponge_db['재질'] == row['재질']]
        
        if material_info.empty:
            return pd.Series(["미등록", "-", 0, 0, 0, 0], index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])

        # 업체별 단가 확정
        is_jinyang = (row['선택업체'] == "진양")
        # 공백이 제거된 컬럼명을 사용하여 KeyError를 방지합니다.
        u_price = float(material_info['가공업체단가' if is_jinyang else '발포업체단가'].values[0])
        calc_mode = "가공업체" if is_jinyang else "발포업체"

        # 수치 데이터 강제 숫자 변환
        ws, w, d, t = float(row['W(사선)']), float(row['W']), float(row['D']), float(row['T'])

        # 소요량 및 재료비
        af_qty = (((ws + w) * d * t) / vol_unit) / 2 if row['재단방식'] == "사선" else (w * d * t) / vol_unit
        ah_mat = af_qty * u_price if calc_mode == "발포업체" else af_qty * (1.0 + loss_rate) * u_price

        # 가공비
        ai_proc = 0.0
        if row['재단방식'] == "2D":
            ai_proc = ah_mat * 0.2
        elif calc_mode != "발포업체":
            if row['재단방식'] == "일반":
                ai_proc = (w/1000 * d/1000 * h_cut) + (w/1000 * d/1000 * t * v_cut)
            elif row['재단방식'] == "사선":
                ai_proc = ((ws + w)/1000 * d/1000 * v_cut * t) + (w/1000 * d/1000 * h_cut)

        # 관리비/이윤 포함 최종단가
        total = (ah_mat + ai_proc + (ai_proc * 0.1)) * (1.0 + admin_rate) * (1.0 + profit_rate)
        final_price = math.floor(total / 10) * 10 if calc_mode == "발포업체" else round(total / 10) * 10
        
        return pd.Series([material_info['밀도'].values[0], material_info['경도'].values[0], round(af_qty, 3), round(ah_mat), round(ai_proc), final_price], 
                         index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])
    except Exception as e:
        # 에러가 나도 웹사이트가 멈추지 않고 에러 내용을 칸에 표시합니다.
        return pd.Series([f"오류:{str(e)[:5]}", "-", 0, 0, 0, 0], index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])

# --- 5. 최종 단가 산출 실행 버튼 ---
st.divider()
if st.button("🚀 최종 단가 산출하기"):
    results = edited_df.apply(calculate_row, axis=1)
    final_df = pd.concat([edited_df, results], axis=1)
    
    # 컬럼 순서 재배치 및 인덱스 1부터 시작
    cols = ["선택업체", "재질", "밀도", "경도", "재단방식", "W(사선)", "W", "D", "T", "소요량(평)", "재료비", "가공비", "최종단가"]
    final_df = final_df[cols]
    final_df.index = range(1, len(final_df) + 1)
    
    st.subheader("📊 산출 결과 리스트")
    st.dataframe(final_df, use_container_width=True)
    st.download_button("📥 결과 저장(CSV)", data=final_df.to_csv(index=True, index_label="No").encode('utf-8-sig'), file_name="sponge_result.csv")
