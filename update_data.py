"""국세청 목록을 가져와 웹앱용 docs/data.json 으로 저장한다. (GitHub Actions에서 주기적으로 실행)"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nts_scrape import TABS, fetch_all

KST = timezone(timedelta(hours=9))
OUT = Path(__file__).parent / "docs" / "data.json"


def main():
    data = fetch_all()
    payload = {
        "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "tabs": [{"name": tab, "items": data[tab]} for tab in TABS],
    }
    new = json.dumps(payload, ensure_ascii=False, indent=1)
    # 글 목록이 그대로면 시간만 바뀐 커밋이 쌓이지 않도록 파일을 건드리지 않음
    if OUT.exists():
        old = json.loads(OUT.read_text(encoding="utf-8"))
        if old.get("tabs") == payload["tabs"]:
            print("변경 없음")
            return
    OUT.write_text(new, encoding="utf-8")
    print("data.json 갱신:", payload["updated"])


if __name__ == "__main__":
    main()
