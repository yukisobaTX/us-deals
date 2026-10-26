#!/usr/bin/env python3
"""Claude が作った要約を deals.json に書き込む(朝の定期実行用)。

入力 JSON: {"<id>": {"what": "10文字以内", "where": "15文字以内", "item": "...", "store": "...",
                     "when": "...", "cond": "..."}, ...}
- what は10文字、where は15文字を超えたら切り詰める(… を付ける)。
- 空の項目は前の要約を残す。地元・家族の記事は jaVia="claude-ev"、ほかは "claude"。
使い方: python3 scripts/apply_summaries.py /tmp/summaries.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEALS = ROOT / "public" / "data" / "deals.json"
FIELDS = ("store", "item", "when", "cond", "what", "where")
LIMIT = {"what": 10, "where": 15, "item": 40}


def clip(t, n):
    t = (t or "").strip()
    return t if len(t) <= n else t[:n - 1] + "…"


def main():
    sums = json.loads(Path(sys.argv[1]).read_text())
    data = json.loads(DEALS.read_text())
    n = 0
    for x in data["items"]:
        v = sums.get(x["id"])
        if not isinstance(v, dict):
            continue
        new = {k: clip(str(v.get(k) or ""), LIMIT.get(k, 30)) for k in FIELDS}
        if not new["what"]:
            continue
        x["sum"] = {**(x.get("sum") or {}), **{k: s for k, s in new.items() if s}}
        x["ja"] = x["sum"].get("item") or x.get("ja") or x["title"]
        x["jaVia"] = "claude-ev" if x.get("region") else "claude"
        n += 1
    DEALS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    print(f"{n} 件を書き込みました")


if __name__ == "__main__":
    main()
