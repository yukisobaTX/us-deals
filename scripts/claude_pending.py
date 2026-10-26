#!/usr/bin/env python3
"""朝の定期実行(Claude)用:要約が必要な記事を書き出す。

朝のメールに載る記事(今日・明日/家族/地元/今後/大型セール)と地元・家族の記事のうち、
「何が(what)・どこで(where)」の要約がないものを JSON で出力する。
Claude はこれを読んで要約を作り、scripts/apply_summaries.py で deals.json に書き込む。

使い方: python3 scripts/claude_pending.py > /tmp/pending.json
"""
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import daily_digest as dd  # noqa: E402

DONE = ("claude", "claude-ev")


def main():
    data = json.loads(dd.DEALS.read_text())
    state = json.loads(dd.STATE.read_text()) if dd.STATE.exists() else {}
    since = state.get("lastSent") or (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat(timespec="minutes").replace("+00:00", "Z")
    picked = {}
    orig = dd.line

    def spy(x, *a, **k):   # メールの各行に使われる記事を拾う
        picked[x["id"]] = x
        return orig(x, *a, **k)
    dd.line = spy
    dd.build(data["items"], since, "")
    dd.line = orig
    for x in data["items"]:   # サイトの地元・家族タブ用(日付が過ぎていないもの)
        if x.get("region") and not x.get("dup") and (x.get("date") or "9999") >= dt.datetime.now(dd.CT).date().isoformat():
            picked.setdefault(x["id"], x)
    out = []
    for x in picked.values():
        sm = x.get("sum") or {}
        if x.get("jaVia") in DONE and sm.get("what"):
            continue
        out.append({"id": x["id"], "kind": "event" if x.get("region") else "deal",
                    "posted": x["posted"][:10], "date": x.get("date"), "title": x["title"], "link": x["link"],
                    "now": {k: sm.get(k, "") for k in ("store", "item", "when", "cond", "what", "where")}})
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"{len(out)} 件", file=sys.stderr)


if __name__ == "__main__":
    main()
