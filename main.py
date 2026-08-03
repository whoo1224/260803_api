import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from zoneinfo import ZoneInfo  # 파이썬 표준 라이브러리 (별도 설치 불필요)

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="역대 박스오피스 (월/일 기준)", page_icon="🎬", layout="wide")

KOBIS_URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"

# 상위 몇 위까지 보여줄지 (요청사항: 1~3위)
TOP_N = 3
# 최근 몇 년치를 조회할지
YEARS_BACK = 10


def fetch_box_office(target_dt: str):
    """
    KOBIS 일별 박스오피스 API를 호출한다.
    성공하면 (True, 영화 리스트) 를 반환하고,
    실패하면 (False, 에러 메시지) 를 반환한다.
    """
    # 1) 발급받은 인증키를 secrets에서 불러온다 (코드에 직접 쓰지 않음!)
    api_key = st.secrets.get("KOBIS_KEY")
    if not api_key:
        return False, "KOBIS_KEY가 secrets에 설정되어 있지 않습니다. Streamlit Cloud의 'Settings > Secrets'에서 KOBIS_KEY 값을 등록해 주세요."

    params = {
        "key": api_key,
        "targetDt": target_dt,
    }

    # 2) 네트워크 요청 (타임아웃, 연결 실패 등 예외 처리)
    try:
        response = requests.get(KOBIS_URL, params=params, timeout=10)
    except requests.exceptions.RequestException as e:
        return False, f"KOBIS 서버에 요청하는 중 문제가 발생했습니다. 인터넷 연결 상태나 KOBIS 서버 상태를 확인해 주세요. (상세: {e})"

    # 3) HTTP 상태 코드 확인 (200이 아니면 서버 자체 문제)
    if response.status_code != 200:
        return False, f"KOBIS 서버가 정상 응답을 주지 않았습니다. (HTTP 상태 코드: {response.status_code}) 잠시 후 다시 시도해 주세요."

    # 4) JSON 파싱 실패 처리
    try:
        data = response.json()
    except ValueError:
        return False, "KOBIS 서버 응답을 JSON으로 해석할 수 없습니다. API 주소나 요청 방식이 올바른지 확인해 주세요."

    # 5) 인증키가 틀려도 상태코드는 200이고, 대신 faultInfo 상자가 온다 -> 반드시 확인
    if "faultInfo" in data:
        fault = data["faultInfo"]
        message = fault.get("message", "알 수 없는 오류")
        return False, f"KOBIS API가 오류를 반환했습니다: {message}. 인증키(KOBIS_KEY)가 올바른지, 발급 상태가 정상인지 확인해 주세요."

    # 6) 정상 구조인지 확인 (boxOfficeResult > dailyBoxOfficeList)
    box_office_result = data.get("boxOfficeResult")
    if box_office_result is None:
        return False, "예상한 형식의 응답이 아닙니다 (boxOfficeResult 없음). KOBIS API 응답 구조가 변경되었을 수 있습니다."

    movie_list = box_office_result.get("dailyBoxOfficeList")
    if movie_list is None:
        return False, "예상한 형식의 응답이 아닙니다 (dailyBoxOfficeList 없음). KOBIS API 응답 구조가 변경되었을 수 있습니다."

    # 7) 영화 목록이 비어서 오는 경우 (예: 해당 날짜에 집계된 데이터가 없음)
    if len(movie_list) == 0:
        return False, "조회된 영화 목록이 비어 있습니다. 해당 날짜의 박스오피스 데이터가 아직 없거나 너무 오래된 날짜일 수 있습니다."

    return True, movie_list


def build_rows(year: int, movie_list):
    """
    특정 연도의 KOBIS 응답(문자열 숫자 포함)에서 상위 TOP_N개만 뽑아
    화면에 보여줄 표용 행(row) 리스트로 변환한다.
    """
    rows = []
    for movie in movie_list[:TOP_N]:
        rows.append({
            "연도": year,
            "순위": movie.get("rank"),
            "영화명": movie.get("movieNm"),
            "개봉일": movie.get("openDt"),
            "관객수": int(movie.get("audiCnt", 0)),
            "누적관객수": int(movie.get("audiAcc", 0)),
            "스크린수": int(movie.get("scrnCnt", 0)),
        })
    return rows


# -----------------------------
# 화면 구성 시작
# -----------------------------
st.title("🎬 역대 박스오피스 (월/일 기준, 최근 10년)")
st.caption(f"원하는 '월/일'을 고르면, 올해를 포함한 최근 {YEARS_BACK}년 동안 같은 날짜의 박스오피스 1~{TOP_N}위를 모아서 보여줍니다.")

# -----------------------------
# 사용자 입력: 월 / 일
# -----------------------------
col_month, col_day = st.columns(2)
with col_month:
    month = st.selectbox("월", list(range(1, 13)), index=0, format_func=lambda m: f"{m}월")
with col_day:
    day = st.selectbox("일", list(range(1, 32)), index=0, format_func=lambda d: f"{d}일")

search_clicked = st.button("조회하기", type="primary")

if not search_clicked:
    st.info("월/일을 선택하고 '조회하기' 버튼을 눌러주세요.")
    st.stop()

# 2월 30일처럼 실제로 존재하지 않는 날짜를 고를 수 있으므로 미리 걸러준다.
# (달력에 없는 조합은 각 연도별로 존재 여부가 다를 수 있어 연도별로 검사한다.)
now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
this_year = now_kst.year

all_rows = []
error_messages = []          # 연도별 조회 실패 사유 모음
invalid_date_years = []      # 그 연도에는 존재하지 않는 날짜(예: 윤년 2/29)

with st.spinner("최근 10년치 데이터를 조회하는 중입니다..."):
    for year in range(this_year - YEARS_BACK + 1, this_year + 1):
        # 해당 연도에 실제로 존재하는 날짜인지 확인 (예: 2월 29일은 윤년에만 존재)
        try:
            datetime(year, month, day)
        except ValueError:
            invalid_date_years.append(year)
            continue

        target_dt = f"{year}{month:02d}{day:02d}"
        ok, result = fetch_box_office(target_dt)

        if not ok:
            error_messages.append(f"- {year}년: {result}")
            continue

        all_rows.extend(build_rows(year, result))

# -----------------------------
# 결과가 하나도 없는 경우: 빈 화면 대신 안내
# -----------------------------
if len(all_rows) == 0:
    st.error("선택하신 날짜로 조회된 데이터가 하나도 없습니다.")
    if error_messages:
        st.warning("연도별 조회 결과를 확인해 주세요:\n" + "\n".join(error_messages))
    if invalid_date_years:
        st.warning(
            f"다음 연도에는 {month}월 {day}일이라는 날짜 자체가 존재하지 않습니다 "
            f"(예: 윤년이 아닌 해의 2월 29일): {', '.join(str(y) for y in invalid_date_years)}"
        )
    st.stop()

# -----------------------------
# 일부만 실패한 경우: 표는 보여주되 상단에 안내
# -----------------------------
if error_messages or invalid_date_years:
    with st.expander("⚠️ 일부 연도는 데이터를 가져오지 못했습니다 (자세히 보기)"):
        if error_messages:
            st.write("**조회 실패:**")
            st.markdown("\n".join(error_messages))
        if invalid_date_years:
            st.write("**날짜 자체가 존재하지 않음:**")
            st.write(", ".join(str(y) for y in invalid_date_years))

# -----------------------------
# 결과 표 출력
# -----------------------------
df = pd.DataFrame(all_rows)
df = df.sort_values(["연도", "순위"], ascending=[False, True]).reset_index(drop=True)

st.subheader(f"📋 {month}월 {day}일 기준, 최근 {YEARS_BACK}년 박스오피스 1~{TOP_N}위")
st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
)
