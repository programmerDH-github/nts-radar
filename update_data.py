"""국세청·재정경제부 목록을 가져와 웹앱용 docs/data.json 으로 저장한다. (GitHub Actions에서 주기적으로 실행)"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nts_scrape import GROUPS, TABS, fetch_all

KST = timezone(timedelta(hours=9))
OUT = Path(__file__).parent / "docs" / "data.json"


def main():
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"tabs": []}
    old_tabs = {t["name"]: t["items"] for t in old["tabs"]}

    # 한 사이트가 잠깐 안 열려도 그 탭은 이전 목록을 유지
    data, errors = fetch_all(fallback=old_tabs)
    for tab, e in errors.items():
        print(f"[경고] {tab} 가져오기 실패 → 이전 목록 유지: {type(e).__name__}: {e}")
    if len(errors) == len(data) - 1:  # '전체'를 뺀 모든 탭 실패
        sys.exit("모든 사이트 접속 실패")

    payload = {
        "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "groups": [{"name": g, "tabs": tabs} for g, tabs in GROUPS.items()],
        "tabs": [{"name": tab, "items": data[tab]} for tab in TABS],
    }
    # 글 목록이 그대로면 시간만 바뀐 커밋이 쌓이지 않도록 파일을 건드리지 않음
    if old.get("tabs") == payload["tabs"] and old.get("groups") == payload["groups"]:
        print("변경 없음")
        return
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print("data.json 갱신:", payload["updated"])


if __name__ == "__main__":
    main()
