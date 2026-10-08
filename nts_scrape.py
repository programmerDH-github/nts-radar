import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36"}

# 접속이 잠깐 끊기거나 느릴 때 몇 번 다시 시도
session = requests.Session()
session.headers.update(HEADERS)
session.mount("https://", HTTPAdapter(max_retries=Retry(
    total=3, connect=3, read=3, backoff_factor=2,
    status_forcelist=[500, 502, 503, 504], allowed_methods=None)))
TIMEOUT = (20, 30)  # (접속, 응답) 초

# ---------- 국세청 ----------
BASE = "https://www.nts.go.kr"

# 국세청 탭 이름 -> 사이트 내부 bbsId
NTS_TABS = {"보도·설명 자료": "B", "공지사항": "1011", "고시": "1120", "공고": "1122"}

# 게시판별 (구분 표시, 링크용 mi 값)
BOARDS = {
    "1028": ("보도", "2201"),
    "1041": ("설명", "2203"),
    "1011": ("공지", "2207"),
    "1120": ("고시", "2205"),
    "1122": ("공고", "2206"),
}


def fetch_tab(bbs_id):
    res = session.post(f"{BASE}/nts/bbsId.do", data={"bbsId": bbs_id}, timeout=TIMEOUT)
    res.raise_for_status()
    items = []
    for x in res.json()["nttList"]:
        kind, mi = BOARDS.get(x["bbsId"], ("기타", ""))
        items.append({
            "id": str(x["nttSn"]),
            "구분": kind,
            "제목": x["nttSj"].strip(),
            "날짜": datetime.strptime(x["regDt"], "%b %d, %Y").strftime("%y.%m.%d."),
            "링크": f"{BASE}/nts/na/ntt/selectNttInfo.do?mi={mi}&bbsId={x['bbsId']}&nttSn={x['nttSn']}",
        })
    return items


# ---------- 재정경제부 세제실 ----------
MOFE = "https://mofe.go.kr"
MOFE_PRESS = "MOSFBBS_000000000028"   # 보도자료 게시판
MOFE_TAX_DEPT = "1051010"             # 세제실


def fetch_mofe_tax():
    """재정경제부 보도자료 중 세제실(조세정책과, 소득세제과 등) 글만 가져온다."""
    res = session.get(f"{MOFE}/nw/nes/nesdta.do", timeout=TIMEOUT, params={
        "searchBbsId1": MOFE_PRESS, "menuNo": "4010100", "searchSilDeptId1": MOFE_TAX_DEPT,
    })
    res.raise_for_status()
    soup = BeautifulSoup(res.content.decode("utf-8"), "html.parser")
    items = []
    for li in soup.select("li"):
        a = li.select_one("h3 a[href*=fn_egov_select]")
        if not a:
            continue
        ntt_id = re.search(r"'(\w+)'", a["href"]).group(1)
        dept = li.select_one(".depart")
        items.append({
            "id": ntt_id,
            "구분": "세제",
            "제목": a.get_text(strip=True) + (f" ({dept.get_text(strip=True)})" if dept else ""),
            "날짜": datetime.strptime(li.select_one(".date").get_text(strip=True), "%Y.%m.%d.").strftime("%y.%m.%d."),
            "링크": f"{MOFE}/nw/nes/detailNesDtaView.do?searchBbsId1={MOFE_PRESS}&searchNttId1={ntt_id}&menuNo=4010100",
        })
    return items


# ---------- 국세법령정보시스템 ----------
TAXLAW = "https://taxlaw.nts.go.kr"


def _taxlaw_doc(it, kind, path):
    """해석례·심판례·판례 한 건을 공통 형식으로 변환"""
    tax = it.get("ntstTlawClCdAbrvNm") or ""
    title = re.sub(r"\s+", " ", it["ntstDcmTtl"]).strip()
    if len(title) > 120:
        title = title[:120] + "…"
    extra = [it["ntstDcmIdNm"]]
    if it.get("subIconNm") and it["subIconNm"] != "해당없음":
        extra.append(it["subIconNm"])   # 인용/기각/국승/국패 등 결과
    return {
        "id": it["ntstDcmId"],
        "구분": kind,
        "제목": f"[{tax}] {title} ({', '.join(extra)})" if tax else f"{title} ({', '.join(extra)})",
        "날짜": datetime.strptime(it["frsRgtDtm"][:8], "%Y%m%d").strftime("%y.%m.%d."),
        "링크": f"{TAXLAW}{path}?ntstDcmId={it['ntstDcmId']}",
    }


def fetch_taxlaw():
    """국세법령정보시스템 메인의 최신 목록(해석례·심판례·판례·개정법령)을 한 번에 가져온다."""
    res = session.post(f"{TAXLAW}/action.do", timeout=TIMEOUT,
                       data={"actionId": "ASECMD001MR01", "paramData": "{}"})
    res.raise_for_status()
    body = res.json()
    if body.get("status") != "SUCCESS":
        raise RuntimeError(f"국세법령정보시스템 응답 오류: {body.get('status')}")
    d = body["data"]["ASECMD001MR01"]
    return {
        "해석례": [_taxlaw_doc(it, "해석", "/qt/USEQTA002P.do") for it in d["ltstTrpThanList"]],
        "심판례": [_taxlaw_doc(it, "심판", "/pd/USEPDA002P.do") for it in d["ltstCntdList"]],
        "판례": [_taxlaw_doc(it, "판례", "/pd/USEPDA002P.do") for it in d["ltstPrtsList"]],
        "개정법령": [{
            "id": "LAW" + it["lnkBrkdId"],
            "구분": "법령",
            "제목": f"{it['stttTtl']} ({it['pmgCntn']})",
            "날짜": datetime.strptime(it["pmgDt"], "%Y%m%d").strftime("%y.%m.%d."),
            "링크": f"{TAXLAW}/st/USESTA003P.do?ntstBscId={it['lnkBscId']}&ntstBrkdId={it['lnkBrkdId']}",
        } for it in d["mainLtstStttList"]],
    }


# ---------- 탭 구성 ----------
# (이 함수가 채우는 탭들, 가져오는 함수) — 함수는 {탭 이름: 목록} 을 돌려줌
# "전체"는 fetch_all에서 직접 합쳐서 만듦
SOURCES = [
    *[([name], lambda n=name, b=bbs_id: {n: fetch_tab(b)}) for name, bbs_id in NTS_TABS.items()],
    (["세제실"], lambda: {"세제실": fetch_mofe_tax()}),
    (["해석례", "심판례", "판례", "개정법령"], fetch_taxlaw),
]

TABS = ["전체", *(tab for tabs, _ in SOURCES for tab in tabs)]

# 화면에서 탭을 묶어 보여줄 단위
GROUPS = {
    "소식": ["전체", *NTS_TABS, "세제실"],
    "법령정보": ["해석례", "심판례", "판례", "개정법령"],
}

# "전체" 탭에서 뺄 탭 (국세법령정보시스템 자료는 참고 자료라 따로 봄)
EXCLUDE_FROM_ALL = {"공고", "해석례", "심판례", "판례", "개정법령"}


def merge_all(data):
    """제외 탭을 뺀 나머지 탭을 합쳐 '전체' 목록을 만든다."""
    merged = {}
    for tab, items in data.items():
        if tab != "전체" and tab not in EXCLUDE_FROM_ALL:
            for it in items:
                merged[it["id"]] = it
    # 날짜(yy.mm.dd.) 최신순, 같은 날짜면 글 번호가 큰(나중에 올린) 순
    return sorted(merged.values(), key=lambda it: (it["날짜"], int(re.sub(r"\D", "", it["id"]))), reverse=True)


def fetch_all(fallback=None):
    """모든 탭을 가져온다. 실패한 탭은 fallback(이전 데이터)이 있으면 그걸 쓰고, 없으면 빈 목록.
    반환: (탭별 데이터, {실패한 탭: 오류})"""
    data, errors = {}, {}
    for tabs, fetch in SOURCES:
        try:
            data.update(fetch())
        except Exception as e:
            for tab in tabs:
                errors[tab] = e
                data[tab] = (fallback or {}).get(tab, [])
    data["전체"] = merge_all(data)
    return {tab: data[tab] for tab in TABS}, errors
