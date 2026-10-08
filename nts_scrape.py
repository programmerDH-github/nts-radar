from datetime import datetime
import requests

BASE = "https://www.nts.go.kr"

# 탭 이름 -> 사이트 내부 bbsId ("전체"는 아래 fetch_all에서 직접 합쳐서 만듦)
TABS = {"전체": None, "보도·설명 자료": "B", "공지사항": "1011", "고시": "1120", "공고": "1122"}

# "전체" 탭에서 뺄 탭
EXCLUDE_FROM_ALL = {"공고"}

# 게시판별 (구분 표시, 링크용 mi 값)
BOARDS = {
    "1028": ("보도", "2201"),
    "1041": ("설명", "2203"),
    "1011": ("공지", "2207"),
    "1120": ("고시", "2205"),
    "1122": ("공고", "2206"),
}


def fetch_tab(bbs_id):
    res = requests.post(f"{BASE}/nts/bbsId.do", data={"bbsId": bbs_id},
                        headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
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


def fetch_all():
    """탭별 목록을 가져오고, '전체'는 공고를 뺀 나머지 탭을 합쳐 최신순으로 만든다."""
    data = {tab: fetch_tab(bbs_id) for tab, bbs_id in TABS.items() if bbs_id}
    merged = {}
    for tab, items in data.items():
        if tab not in EXCLUDE_FROM_ALL:
            for it in items:
                merged[it["id"]] = it
    # 날짜(yy.mm.dd.) 최신순, 같은 날짜면 글 번호가 큰(나중에 올린) 순
    data["전체"] = sorted(merged.values(), key=lambda it: (it["날짜"], int(it["id"])), reverse=True)
    return data
