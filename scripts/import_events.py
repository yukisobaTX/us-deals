#!/usr/bin/env python3
"""カレッジステーション周辺のイベント一覧を deals.json に取り込む(朝の定期実行・Claude 用)。

GitHub Actions からは Destination Bryan・ブライアン市のイベント一覧が取れない(403 や空の画面)ため、
Claude の定期実行が Firecrawl で一覧を読み、次の JSON にまとめてこのスクリプトで取り込む。

入力 JSON(配列):
  [{"title": "英語の催し名", "link": "https://...", "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"|null,
    "category": "Family-Friendly など(任意)", "source": "Destination Bryan" | "City of Bryan",
    "what": "10文字以内", "where": "15文字以内", "item": "40文字以内の要約", "when": "10/31(土) 10時", "cond": ""}, ...]
- A&M のスポーツ・夜の店の定例・会議は fetch_deals.outing_ng() で外す。
- 既にある催しは開催日・終了日・要約を更新する。新しい催しは region=College Station、calendar=true で追加。
- 開催日が過ぎた催しは fetch_deals.py の通常の掃除(expires)で消える。
使い方: python3 scripts/import_events.py /tmp/events.json
"""
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_deals as fd  # noqa: E402

DEALS = fd.OUT
LIMIT = {"what": 10, "where": 15, "item": 40}


def clip(t, n):
    t = (t or "").strip()
    return t if len(t) <= n else t[:n - 1] + "…"


def main():
    events = json.loads(Path(sys.argv[1]).read_text())
    data = json.loads(DEALS.read_text())
    by_id = {x["id"]: x for x in data["items"]}
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes").replace("+00:00", "Z")
    today = dt.datetime.now(fd.CT).date().isoformat()
    added = updated = skipped = 0
    seen = set()
    for e in events:
        title, link, start = (e.get("title") or "").strip(), (e.get("link") or "").strip(), e.get("start")
        if not title or not link.startswith("https://") or not start:
            skipped += 1
            continue
        cats = [c for c in [e.get("category")] if c]
        if fd.outing_ng(title, cats) or (e.get("end") or start) < today:
            skipped += 1
            continue
        iid = hashlib.sha1(link.split("?")[0].rstrip("/").encode()).hexdigest()[:12]
        sm = {k: clip(str(e.get(k) or ""), LIMIT.get(k, 30)) for k in ("store", "item", "when", "cond", "what", "where")}
        sm = {k: v for k, v in sm.items() if v}
        x = by_id.get(iid)
        if x and iid in seen:
            # 同じ催しが一覧に何度も出る(毎日開催など):いちばん早い開催日・いちばん遅い終了日を残す
            x["localDate"] = min(x["localDate"], start)
            x["expires"] = max(x.get("expires") or start, e.get("end") or start)
            continue
        seen.add(iid)
        if x:
            x["localDate"], x["expires"] = start, e.get("end") or start
            if sm.get("what"):
                x["sum"] = {**(x.get("sum") or {}), **sm}
                x["ja"], x["jaVia"] = x["sum"].get("item") or x.get("ja") or title, "claude-ev"
            updated += 1
            continue
        x = {"id": iid, "title": title, "link": link, "source": e.get("source") or "Destination Bryan",
             "posted": now, "firstSeen": now, "expires": e.get("end") or start, "thumb": e.get("thumb"),
             "noAlert": True, "region": "College Station", "localDate": start, "calendar": True,
             "hot": False, "stores": [], "cats": cats or ["other"], "types": ["sale"], "pct": None, "price": None,
             "event": None, "eventNews": False}
        if sm.get("what"):
            x["sum"], x["ja"], x["jaVia"] = sm, sm.get("item") or title, "claude-ev"
        kinds = fd.outing_kinds(title, cats + [x["source"]])
        if kinds:
            x["outing"], x["family"] = kinds, True
        x["date"] = start
        data["items"].append(x)
        by_id[iid] = x
        seen.add(iid)
        added += 1
    data["count"] = len(data["items"])
    DEALS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    print(f"追加 {added} 件・更新 {updated} 件・除外 {skipped} 件")


if __name__ == "__main__":
    main()
