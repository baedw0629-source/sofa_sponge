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
        # utf-8-sig로 인코딩 문제 해결
        df = pd.read_csv('spongematerials.csv', encoding='utf-8-sig')
        
        # 1. 컬럼명 정제: 앞뒤 공백 제거 및 모든 중간 공백 제거
        df.columns = df.columns.str.strip().str.replace(' ', '').str.replace('\t', '')
        
        # 2. 데이터 값 정제: 숫자 컬럼에서 콤마, 원, 공백 제거 후 강제 숫자 변환
        price_cols = ['가공업체단가', '발포업체단가']
        for col in price_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '').str.replace('원', '').str.strip()
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        
        # 3. 기타 정보 문자열화
        for col in ['재질', '밀도', '경도']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        
        return df
    except Exception as e:
        st.error(f"⚠️ 파일 로드 중 심각한 오류 발생: {e}")
        return pd.DataFrame()

# 캐시 초기화 버튼 (사이드바)
if st.sidebar.button("♻️ 데이터 강제 새로고침"):
    st.cache_data.clear()
    st.rerun()

sponge_db = load_data()

# --- 2. 시스템 기준 설정 ---
st.sidebar.header("⚙️ 시스템 기준 설정")
h_cut = st.sidebar.number_input("수평재단비 (원)", value=20.0, format="%.1f")
v_cut = st.sidebar.number_input("수직재단비 (원)", value=11.0, format="%.1f")
loss_rate = st.sidebar.number_input("로스율 (%)", value=5.0, format="%.1f") / 100
admin_rate = st.sidebar.number_input("일반관리비율 (%)", value=5.0, format="%.1f") / 100
profit_rate = st.sidebar.number_input("이윤율 (%)", value=10.0, format="%.1f") / 100

# --- 3. 입력 창 ---
st.title("🧽 스펀지 단가 산출 TOOL")

if "input_df" not in st.session_state:
    st.session_state.input_df = pd.DataFrame([{
        "선택업체": "진양", "재질": "선택하세요", "재단방식": "일반",
        "W(사선)": 0.0, "W": 500.0, "D": 400.0, "T": 300.0
    }])

# 재질 목록 생성
material_list = ["선택하세요"]
if not sponge_db.empty and '재질' in sponge_db.columns:
    material_list += sponge_db['재질'].unique().tolist()

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

# --- 4. 계산 엔진 (에러 방지 강화) ---
def calculate_row(row):
    # 재질 미선택 시 빈 값 반환
    if row['재질'] == "선택하세요" or row['재질'] == "":
        return pd.Series(["-", "-", 0, 0, 0, 0], index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])
    
    try:
        vol_unit = 303 * 303 * 10
        material_info = sponge_db[sponge_db['재질'] == row['재질']]
        
        if material_info.empty:
            return pd.Series(["미등록", "-", 0, 0, 0, 0], index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])

        # 1. 업체별 단가 확정 (KeyError 방지 로직)
        is_jinyang = (row['선택업체'] == "진양")
        price_col = '가공업체단가' if is_jinyang else '발포업체단가'
        
        if price_col not in material_info.columns:
            return pd.Series([f"컬럼없음:{price_col}", "-", 0, 0, 0, 0], index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])
            
        u_price = float(material_info[price_col].values[0])
        calc_mode = "가공업체" if is_jinyang else "발포업체"

        # 2. 모든 입력값을 강제로 float으로 변환하여 TypeError 방지
        ws = float(row.get('W(사선)', 0))
        w = float(row.get('W', 0))
        d = float(row.get('D', 0))
        t = float(row.get('T', 0))

        # 3. 소요량(AF)
        af_qty = (((ws + w) * d * t) / vol_unit) / 2 if row['재단방식'] == "사선" else (w * d * t) / vol_unit
        
        # 4. 재료비(AH)
        ah_mat = af_qty * u_price if calc_mode == "발포업체" else af_qty * (1.0 + loss_rate) * u_price

        # 5. 가공비(AI)
        ai_proc = 0.0
        if row['재단방식'] == "2D":
            ai_proc = ah_mat * 0.2
        elif calc_mode != "발포업체":
            if row['재단방식'] == "일반":
                ai_proc = (w/1000 * d/1000 * h_cut) + (w/1000 * d/1000 * t * v_cut)
            elif row['재단방식'] == "사선":
                ai_proc = ((ws + w)/1000 * d/1000 * v_cut * t) + (w/1000 * d/1000 * h_cut)

        # 6. 경비/관리비/이윤/최종단가
        aj_exp = ai_proc * 0.1
        ak_admin = 0.0 if calc_mode == "발포업체" else (ah_mat + ai_proc + aj_exp) * admin_rate
        al_profit = (ai_proc + aj_exp + ak_admin) * profit_rate
        total = ah_mat + ai_proc + aj_exp + ak_admin + al_profit
        
        final_price = math.floor(total / 10) * 10 if calc_mode == "발포업체" else round(total / 10) * 10
        
        d_val = material_info['밀도'].values[0] if '밀도' in material_info.columns else "-"
        h_val = material_info['경도'].values[0] if '경도' in material_info.columns else "-"

        return pd.Series([d_val, h_val, round(af_qty, 3), round(ah_mat), round(ai_proc), final_price], 
                         index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])
    except Exception as e:
        return pd.Series([f"에러:{str(e)[:10]}", "-", 0, 0, 0, 0], index=["밀도", "경도", "소요량(평)", "재료비", "가공비", "최종단가"])

# --- 5. 산출 및 결과 ---
st.divider()
if st.button("🚀 최종 단가 산출하기"):
    if not edited_df.empty:
        results = edited_df.apply(calculate_row, axis=1)
        final_df = pd.concat([edited_df, results], axis=1)
        
        # 순서 재배치
        cols = ["선택업체", "재질", "밀도", "경도", "재단방식", "W(사선)", "W", "D", "T", "소요량(평)", "재료비", "가공비", "최종단가"]
        final_df = final_df[cols]
        final_df.index = range(1, len(final_df) + 1)
        
        st.subheader("📊 산출 결과 리스트")
        st.dataframe(final_df, use_container_width=True)
        
        # CSV 다운로드 (BOM 포함하여 엑셀 한글 깨짐 방지)
        csv = final_df.to_csv(index=True, index_label="No").encode('utf-8-sig')
        st.download_button("📥 결과 저장(CSV)", data=csv, file_name="sponge_result.csv", mime="text/csv")
    else:
        st.warning("데이터를 입력해 주세요.")

# --- 6. [진단 도드] 에러 해결을 위한 데이터 확인 창 ---
with st.expander("🛠️ 시스템 진단 도구 (에러 발생 시 확인용)"):
    if not sponge_db.empty:
        st.write("✅ 파일 로드 성공!")
        st.write("현재 인식된 컬럼명:", list(sponge_db.columns))
        st.write("데이터 샘플 (상위 3개):")
        st.dataframe(sponge_db.head(3))
    else:
        st.error("❌ 파일을 찾을 수 없거나 형식이 잘못되었습니다.")
