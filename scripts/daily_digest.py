#!/usr/bin/env python3
"""毎朝のまとめを Gmail で1通だけ送る(送れないときだけ GitHub Issue)。

- 2026-10-26 から通知は朝の1通だけ(即時通知 freebie_alert.py は廃止)。
- 今日・明日の無料情報(店頭・クーポン・飲食 BOGO)は「店舗名:もらえるもの:日時:条件」とリンクで詳しく。
  日付なしの新着も「今すぐ使える」としてここに入れる。
- 明後日〜2週間先の無料情報と大型セールの新着は、日付と内容の短文だけ。詳細はサイトで見る。
- 前の Issue は閉じない(閉じると完了通知メールが別に届くため)。
- 夏時間・冬時間の両方に対応するため、cron は2つ(12:08・13:08 UTC)で起動し、
  米国中部時間で 7 時台のときだけ送る(--force で時刻を無視)。

環境変数:GITHUB_TOKEN、GITHUB_REPOSITORY、SITE_URL(任意)
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DEALS = ROOT / "public" / "data" / "deals.json"
STATE = ROOT / "public" / "data" / "digest-state.json"
STORES = ROOT / "config" / "stores.json"
CT = ZoneInfo("America/Chicago")
LABEL = "deals-digest"
MENTION = "@yukisobaTX"
HORIZON_DAYS = 14   # この先の予定に載せる範囲
MAX_LATER = 15
TYPE_JA = {"free": "無料", "bogo": "BOGO", "coupon": "クーポン", "gc": "ギフトカード", "sale": "セール"}


def api(method, path, body=None):
    repo = os.environ["GITHUB_REPOSITORY"]
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                 "Accept": "application/vnd.github+json", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        t = r.read()
        return json.loads(t) if t else None


WD = "月火水木金土日"


def md(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.month}/{d.day}({WD[d.weekday()]})"


def sum_parts(x, today):
    """店舗名・もらえるもの・日時・条件(空は —)。"""
    sm = x.get("sum") or {}
    store = sm.get("store") or "・".join(n for n in x["stores"][:2] if n != "レストラン全般") or "—"
    item = sm.get("item") or x.get("ja") or x["title"]
    when = sm.get("when") or ""
    if x.get("date") == today and not when.startswith("〜"):
        when = "今日 " + when.split(" ", 1)[1] if " " in when else "今日"
    return store, item, when or "—", sm.get("cond") or "—"


def by_date(xs):
    """日付順(配布日・期限が近い順、日付なしは後ろ)。"""
    return sorted(xs, key=lambda x: (x.get("date") or "9999", x["posted"]))


def fmt_item(x, today):
    store, item, when, cond = sum_parts(x, today)
    when = f"**{when}**" if when.startswith("今日") else when
    kind = (x.get("freebie") or {}).get("kind")
    icon = "🏬" if kind == "store" else "🎟" if kind else "🛍"
    if (x.get("freebie") or {}).get("bogo"):
        icon += "🥤BOGO"
    return f"- {icon} **{store}**:[{item}]({x['link']}):{when}:{cond}"


def short_line(x, label=""):
    """この先の分:日付と内容だけの短い1行(詳細はサイトで見る)。label ありは大型セールの記事(日付は付けない)。"""
    store, item, _, _ = sum_parts(x, "")
    icon = "🥤" if (x.get("freebie") or {}).get("bogo") else ""
    head = label or (md(x["date"]) if x.get("date") else "日付未定")
    who = f"{store}:" if store != "—" else ""
    return f"- {head} {who}{icon}{item[:40]}"


# 購入が条件の「無料」(〜ドル以上の購入で無料、2つ買うと2つ無料、購入特典など)。飲食の BOGO は別扱いで残す
NEEDS_PURCHASE_RE = re.compile(
    r"w(?:ith)?/?\s*(?:any\s+|a\s+|\$[\d.]+\+?\s+)?(?:purchase|order)|purchase of|\$[\d.]+\+?\s+purchase|"
    r"\bspend\s+\$|\bbuy\s+(?:one|two|three|\d+)\b.*\bget\b|\bB\dG\d\b|gift with purchase|when you (?:buy|spend)|"
    r"\bunlock\b", re.I)


def is_pure_free(x):
    """メールの「今日・明日」に載せるのは、完全無料(購入不要)と飲食の BOGO だけ。"""
    fb = x.get("freebie") or {}
    if fb.get("bogo"):
        return True
    cond = (x.get("sum") or {}).get("cond") or ""
    if re.search(r"no purchase (?:necessary|required)", x["title"], re.I) or re.search(r"購入(?:は)?(?:不要|必要(?:ありません|なし))", (x.get("ja") or "") + cond):
        return True
    return not NEEDS_PURCHASE_RE.search(x["title"]) and "購入" not in cond and "購入" not in (x.get("ja") or "")


def build(items, since, site):
    """朝の1通。今日・明日の無料情報は詳しく、それ以降は日付と内容の短文だけ(詳細はサイト)。"""
    today = dt.datetime.now(CT).date()
    t_iso = today.isoformat()
    tomorrow = (today + dt.timedelta(days=1)).isoformat()
    horizon = (today + dt.timedelta(days=HORIZON_DAYS)).isoformat()
    fbs = [x for x in items if x.get("freebie") and not x.get("dup") and not x.get("noAlert")]
    # 今日・明日:日付が今日・明日のもの(前に載せたものも毎回)+日付なしの新着(今すぐ使える)
    near = [x for x in fbs if x.get("date") in (t_iso, tomorrow)
            or (not x.get("date") and x["firstSeen"] > since)]
    near = by_date([x for x in near if is_pure_free(x)])
    # この先:明後日〜2週間先の無料情報(短文のみ。毎朝の予定表として繰り返し載せる)
    later = by_date([x for x in fbs if x.get("date") and tomorrow < x["date"] <= horizon])[:MAX_LATER]
    # 大型セール:前回のまとめ以降の記事を、セールごとに最大3件(短文のみ)
    ev_labels = {e["id"]: e["label"] for e in json.loads(STORES.read_text()).get("events", [])}
    ev_lines = []
    for eid, lab in ev_labels.items():
        g = sorted([x for x in items if x.get("event") == eid and x["firstSeen"] > since
                    and not x.get("freebie") and not x.get("dup")],
                   key=lambda x: x["posted"], reverse=True)
        ev_lines += [short_line(x, f"【{lab}】") for x in g[:3]]
    n = len(near) + len(later) + len(ev_lines)
    title = f"お得ノート {today.month}/{today.day}:今日・明日 {len(near)}件" + (f" / この先 {len(later)}件" if later else "")
    lines = [f"{MENTION} おはようございます。今日・明日の無料情報です(購入不要の無料と🥤BOGO=1つ買うと1つ無料だけ。🏬店頭・🎟クーポン)。",
             *([f"一覧: {site}"] if site else []), "", f"## 🎁 今日・明日({md(t_iso)}・{md(tomorrow)})"]
    lines += [fmt_item(x, t_iso) for x in near] or ["- 該当なし"]
    if later or ev_lines:
        lines += ["", "## 📅 この先の予定(詳細はサイトで)", *[short_line(x) for x in later]]
        if ev_lines:
            lines += ["", "🛍 大型セール", *ev_lines]
        if site:
            lines += [f"詳細: {site}"]
    lines += ["", "---", "店舗ごとに実施が違うことがあるので、リンク先・お店の公式で確認してください。"]
    return title, "\n".join(lines), n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="時刻の判定をしない")
    ap.add_argument("--dry-run", action="store_true", help="Issue を作らず本文を表示")
    a = ap.parse_args()

    now_ct = dt.datetime.now(CT)
    if not a.force and now_ct.hour != 7:
        print(f"skip: CT {now_ct:%H:%M}(7時台だけ送る)")
        return
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    if not a.force and state.get("lastDate") == now_ct.date().isoformat():
        print("skip: 今日は送信済み")
        return
    data = json.loads(DEALS.read_text())
    since = state.get("lastSent") or (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat(timespec="minutes").replace("+00:00", "Z")
    title, body, n = build(data["items"], since, os.environ.get("SITE_URL", ""))
    if data.get("errors"):
        body += "\n\n⚠️ 取得できなかった情報源: " + " / ".join(data["errors"])
    if n == 0 and not a.force:
        print("skip: 載せる情報なし(メールは送らない)")
        STATE.write_text(json.dumps({**state, "lastSent": data["updated"], "lastDate": now_ct.date().isoformat()}, ensure_ascii=False, indent=1) + "\n")
        return
    if a.dry_run:
        print(title)
        print(body)
        return

    try:
        api("POST", "/labels", {"name": LABEL, "color": "f9a825", "description": "毎朝のお得情報まとめ"})
    except Exception:  # noqa: BLE001  既にある
        pass
    # Gmail から直接送る(件名に [リポジトリ名]・(Issue #番号) が付かない)。送れないときだけ GitHub の Issue 通知
    import mailer
    if mailer.send_mail(title, body.replace(MENTION + " ", "")):
        created = {"number": None}
    else:
        # 前の Issue は閉じない(閉じると「Closed as completed」の通知メールが別に届くため)
        created = api("POST", "/issues", {"title": title, "body": body, "labels": [LABEL]})
    print(f"Issue #{created['number']} を作成({n} 件)")
    STATE.write_text(json.dumps({"lastSent": data["updated"], "lastDate": now_ct.date().isoformat(),
                                 "lastIssue": created["number"]}, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    sys.exit(main())
