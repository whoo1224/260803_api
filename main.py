"""
어제자 박스오피스 조회 앱 (KOBIS 오픈API 사용)
- Streamlit Cloud 배포용
- 인증키는 st.secrets["KOBIS_KEY"]에서 불러온다 (코드에 직접 쓰지 않음)
"""

import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo  # 파이썬 표준 라이브러리 (별도 설치 불필요)

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="어제의 박스오피스", page_icon="🎬", layout="wide")

KOBIS_URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"


def get_yesterday_kst() -> str:
    """
    '어제' 날짜를 한국 시간(KST) 기준으로 계산해서 yyyymmdd 형식 문자열로 반환.
    배포 서버의 시계가 한국 시간이 아니어도 항상 한국 기준으로 '어제'를 구하기 위해
    ZoneInfo("Asia/Seoul")를 사용한다.
    """
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    yesterday_kst = now_kst - timedelta(days=1)
    return yesterday_kst.strftime("%Y%m%d")


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
        return False, "조회된 영화 목록이 비어 있습니다. 아직 해당 날짜의 박스오피스 데이터가 집계되지 않았을 수 있으니, 잠시 후 다시 시도해 주세요."

    return True, movie_list


def build_dataframe(movie_list):
    """
    KOBIS 응답(문자열 숫자 포함)을 화면에 보여줄 표용 데이터프레임으로 변환한다.
    """
    rows = []
    for movie in movie_list:
        rows.append({
            "순위": movie.get("rank"),
            "영화명": movie.get("movieNm"),
            "개봉일": movie.get("openDt"),
            "관객수": int(movie.get("audiCnt", 0)),
            "누적관객수": int(movie.get("audiAcc", 0)),
            "스크린수": int(movie.get("scrnCnt", 0)),
        })
    df = pd.DataFrame(rows)
    return df


# -----------------------------
# 화면 구성 시작
# -----------------------------
st.title("🎬 어제의 박스오피스")

target_dt = get_yesterday_kst()
# 화면에 조회 날짜를 사람이 보기 편한 형태로 표시 (yyyymmdd -> yyyy-mm-dd)
pretty_date = f"{target_dt[0:4]}-{target_dt[4:6]}-{target_dt[6:8]}"
st.caption(f"조회 기준일 (한국 시간 기준 어제): {pretty_date}")

with st.spinner("박스오피스 정보를 불러오는 중입니다..."):
    ok, result = fetch_box_office(target_dt)

# 실패한 경우: 빈 화면 대신 무엇을 확인해야 하는지 안내
if not ok:
    st.error("박스오피스 정보를 불러오지 못했습니다.")
    st.warning(result)
    st.stop()

movie_list = result
df = build_dataframe(movie_list)

# -----------------------------
# 1위 영화: 지표 카드 세 장
# -----------------------------
top_movie = df.iloc[0]
st.subheader(f"🥇 1위: {top_movie['영화명']}")

col1, col2, col3 = st.columns(3)
col1.metric("어제 관객수", f"{top_movie['관객수']:,} 명")
col2.metric("누적 관객수", f"{top_movie['누적관객수']:,} 명")
col3.metric("스크린수", f"{top_movie['스크린수']:,} 개")

st.divider()

# -----------------------------
# 전체 순위표
# -----------------------------
st.subheader("📋 전체 순위표")
st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
)

st.divider()

# -----------------------------
# 관객수 상위 5편 막대그래프
# -----------------------------
st.subheader("📊 관객수 상위 5편")
top5 = df.sort_values("관객수", ascending=False).head(5)
chart_data = top5.set_index("영화명")["관객수"]
st.bar_chart(chart_data)
