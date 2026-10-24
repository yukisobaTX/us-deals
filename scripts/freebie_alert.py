#!/usr/bin/env python3
"""「無料でもらえるもの」の新着を、見つけ次第 Issue で通知する(@ でメールが届く)。

収集(Collect deals、毎時)の直後に実行する。
- 対象:前回の通知以降に見つかった freebie(firstSeen > lastAlert)。日付が過ぎたものは除く。
- 新着がなければ何もしない。
- 前の通知 Issue は閉じる(メールは届いているので受信箱に溜めない)。
- 状態は public/data/alert-state.json。初回(状態なし)は通知せず基準点だけ記録する。

環境変数:GITHUB_TOKEN、GITHUB_REPOSITORY、SITE_URL(任意)
"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from daily_digest import CT, DEALS, MENTION, api, fmt_item  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "public" / "data" / "alert-state.json"
LABEL = "freebie-alert"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    data = json.loads(DEALS.read_text())
    state = json.loads(STATE.read_text()) if STATE.exists() else None
    if state is None:
        STATE.write_text(json.dumps({"lastAlert": data["updated"]}, indent=1) + "\n")
        print("初回:基準点だけ記録(通知しない)")
        return
    today = dt.datetime.now(CT).date().isoformat()
    new = [x for x in data["items"] if x.get("freebie") and x["firstSeen"] > state["lastAlert"]
           and (x["freebie"]["when"] or "9999") >= today]
    if not new:
        print("無料の新着なし")
        STATE.write_text(json.dumps({**state, "lastAlert": data["updated"]}, indent=1) + "\n")
        return
    new.sort(key=lambda x: (x["freebie"]["kind"] != "store", x["freebie"]["when"] or "9999"))
    store = [x for x in new if x["freebie"]["kind"] == "store"]
    coupon = [x for x in new if x["freebie"]["kind"] == "coupon"]
    soon = [x for x in store if x["freebie"]["when"] == today]
    head = "🎁 無料情報" + (" ⏰今日" if soon else "")
    title = f"{head}:" + "・".join([f"店頭{len(store)}"] * bool(store) + [f"クーポン{len(coupon)}"] * bool(coupon)) \
        + " / " + (new[0].get("ja") or new[0]["title"])[:40]
    lines = [f"{MENTION} 無料でもらえる新着です。", ""]
    if store:
        lines += ["## 🏬 店頭でもらえる", *[fmt_item(x, today) for x in store], ""]
    if coupon:
        lines += ["## 🎟 無料クーポン・アプリ", *[fmt_item(x, today) for x in coupon], ""]
    site = os.environ.get("SITE_URL", "")
    if site:
        lines += [f"一覧: {site}", ""]
    lines += ["---", "店舗ごとに実施が違うことがあるので、リンク先・お店の公式で確認してください。"]
    body = "\n".join(lines)
    if a.dry_run:
        print(title)
        print(body)
        return
    try:
        api("POST", "/labels", {"name": LABEL, "color": "d73a4a", "description": "無料でもらえるものの即時通知"})
    except Exception:  # noqa: BLE001  既にある
        pass
    for old in api("GET", f"/issues?labels={LABEL}&state=open&per_page=50") or []:
        api("PATCH", f"/issues/{old['number']}", {"state": "closed", "state_reason": "completed"})
    created = api("POST", "/issues", {"title": title, "body": body, "labels": [LABEL]})
    print(f"Issue #{created['number']} を作成({len(new)} 件)")
    STATE.write_text(json.dumps({"lastAlert": data["updated"], "lastIssue": created["number"]}, indent=1) + "\n")


if __name__ == "__main__":
    sys.exit(main())
