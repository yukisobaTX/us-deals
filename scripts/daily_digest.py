#!/usr/bin/env python3
"""毎朝のまとめを GitHub Issue で送る(冒頭の @ で通知メールが届く)。

- 対象:無料でもらえるもの。新着は毎時の即時通知(freebie_alert.py)で送るので、
  朝は「今日・明日の店頭配布」のリマインドと、即時通知されていない新着だけ。
- 前の Issue は閉じない(閉じると完了通知メールが別に届くため)。
- 夏時間・冬時間の両方に対応するため、cron は2つ(12:08・13:08 UTC)で起動し、
  米国中部時間で 7 時台のときだけ送る(--force で時刻を無視)。

環境変数:GITHUB_TOKEN、GITHUB_REPOSITORY、SITE_URL(任意)
"""
import argparse
import datetime as dt
import json
import os
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
MAX_PER_CAT = 12
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
    return f"- {icon} **{store}**:[{item}]({x['link']}):{when}:{cond}<br><sub>{x['title']}</sub>"


def build(items, since, site):
    """無料でもらえるもの(店頭配布・無料クーポン)だけを送る。"""
    today = dt.datetime.now(CT).date()
    t_iso = today.isoformat()
    tomorrow = (today + dt.timedelta(days=1)).isoformat()
    fbs = [x for x in items if x.get("freebie")]
    # 店頭:新着、または今日・明日のもの(前に知らせたものも当日にもう一度)
    store = [x for x in fbs if x["freebie"]["kind"] == "store"
             and (x["freebie"]["when"] or "9999") >= t_iso
             and (x["firstSeen"] > since or x["freebie"]["when"] in (t_iso, tomorrow))]
    store += [x for x in fbs if x["freebie"]["kind"] == "store" and not x["freebie"]["when"] and x["firstSeen"] > since and x not in store]
    store.sort(key=lambda x: x["freebie"]["when"] or "9999")
    coupon = [x for x in fbs if x["freebie"]["kind"] == "coupon" and x["firstSeen"] > since
              and (x["freebie"]["when"] or "9999") >= t_iso]
    coupon.sort(key=lambda x: x["freebie"]["when"] or "9999")
    allx = by_date(store + coupon)
    # 大型セール:前回のまとめ以降の記事を、セールごとに新しい順で最大5件
    ev_labels = {e["id"]: e["label"] for e in json.loads(STORES.read_text()).get("events", [])}
    ev_lines = []
    for eid, lab in ev_labels.items():
        g = sorted([x for x in items if x.get("event") == eid and x["firstSeen"] > since and not x.get("freebie")],
                   key=lambda x: x["posted"], reverse=True)
        if g:
            ev_lines += [f"**{lab}**({len(g)}件)", *[fmt_item(x, t_iso) for x in g[:5]], ""]
    n = len(allx) + len(ev_lines)
    title = f"無料でもらえる {today.month}/{today.day}:店頭{len(store)}・クーポン{len(coupon)}"
    lines = [f"{MENTION} おはようございます。無料でもらえるもの(日付順、🏬店頭・🎟クーポン)です。",
             *([f"一覧: {site}"] if site else []), ""]
    lines += [fmt_item(x, t_iso) for x in allx] + [""]
    if ev_lines:
        lines += ["## 🛍 大型セール", *ev_lines]
    lines += ["---", "見出しとリンクは各ブログの RSS から自動で集めています。店舗ごとに実施が違うことがあるので、リンク先・お店の公式で確認してください。"]
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
    alert = ROOT / "public" / "data" / "alert-state.json"
    alerted = json.loads(alert.read_text()).get("lastAlert", "") if alert.exists() else ""
    since = max(state.get("lastSent") or "", alerted) or (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat(timespec="minutes").replace("+00:00", "Z")
    title, body, n = build(data["items"], since, os.environ.get("SITE_URL", ""))
    if data.get("errors"):
        body += "\n\n⚠️ 取得できなかった情報源: " + " / ".join(data["errors"])
    if n == 0 and not a.force:
        print("skip: 無料の新着なし(メールは送らない)")
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
