#!/usr/bin/env python3
"""「無料でもらえるもの」の新着を、見つけ次第 Issue で通知する(@ でメールが届く)。

収集(Collect deals、毎時)の直後に実行する。
- 対象:前回の通知以降に見つかった freebie(firstSeen > lastAlert)。日付が過ぎたものは除く。
- 新着がなければ何もしない。
- 前の Issue は閉じない(閉じると完了通知メールが別に届くため)。
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
from daily_digest import CT, DEALS, MENTION, api, by_date, fmt_item  # noqa: E402

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
    new = [x for x in data["items"] if x.get("freebie") and not x.get("noAlert") and not x.get("dup") and x["firstSeen"] > state["lastAlert"]
           and (x["freebie"]["when"] or "9999") >= today]
    # 大型セール(ブラックフライデー・プライムデー等)の日程発表・開始・チラシ公開
    events = by_date([x for x in data["items"] if x.get("eventNews") and not x.get("freebie") and not x.get("noAlert") and not x.get("dup")
                      and x["firstSeen"] > state.get("lastEvent", "2000")])[:8]
    if not new and not events:
        print("無料の新着なし")
        STATE.write_text(json.dumps({**state, "lastAlert": data["updated"], "lastEvent": data["updated"]}, indent=1) + "\n")
        return
    new = by_date(new)
    store = [x for x in new if x["freebie"]["kind"] == "store"]
    coupon = [x for x in new if x["freebie"]["kind"] == "coupon"]
    soon = [x for x in store if x["freebie"]["when"] == today]
    parts = []
    if events:
        parts.append(f"🛍 大型セール{len(events)}")
    if new:
        parts.append("🎁 無料" + "・".join([f"店頭{len(store)}"] * bool(store) + [f"クーポン{len(coupon)}"] * bool(coupon)))
    first = (events or new)[0]
    title = ("⏰今日 " if soon else "") + " / ".join(parts) + " / " + (first.get("ja") or first["title"])[:40]
    site = os.environ.get("SITE_URL", "")
    lines = [f"{MENTION} 新着のお知らせです。", *([f"一覧: {site}"] if site else []), ""]
    if events:
        lines += ["## 🛍 大型セール(日程発表・開始など)", *[fmt_item(x, today) for x in events], ""]
    if new:
        lines += ["## 🎁 無料でもらえる(日付順、🏬店頭・🎟クーポン・🥤BOGO=1つ買うと1つ無料)", *[fmt_item(x, today) for x in new], ""]
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
    # Gmail から直接送る(件名に [リポジトリ名]・(Issue #番号) が付かない)。送れないときだけ GitHub の Issue 通知
    import mailer
    if mailer.send_mail(title, body.replace(MENTION + " ", "")):
        created = {"number": None}
    else:
        # 前の Issue は閉じない(閉じると「Closed as completed」の通知メールが別に届くため)
        created = api("POST", "/issues", {"title": title, "body": body, "labels": [LABEL]})
    print(f"Issue #{created['number']} を作成(無料 {len(new)} 件・大型セール {len(events)} 件)")
    STATE.write_text(json.dumps({"lastAlert": data["updated"], "lastEvent": data["updated"],
                                 "lastIssue": created["number"]}, indent=1) + "\n")


if __name__ == "__main__":
    sys.exit(main())
