#!/usr/bin/env python3
"""毎朝のまとめを GitHub Issue で送る(冒頭の @ で通知メールが届く)。

- 対象:前回のまとめ以降に見つかった記事(firstSeen)。
- 「注目」(無料・70%以上)を先に、カテゴリごとに並べる。
- 前のまとめ Issue は閉じる(受信箱に溜めない)。
- 夏時間・冬時間の両方に対応するため、cron は2つ(12:41・13:41 UTC)で起動し、
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


def fmt_item(x):
    tags = [TYPE_JA[t] for t in x["types"] if t in TYPE_JA and t != "sale"]
    if x.get("pct"):
        tags.append(f"{x['pct']}%OFF")
    if x.get("expires"):
        d = dt.date.fromisoformat(x["expires"])
        tags.append(f"〜{d.month}/{d.day}")
    store = "・".join(x["stores"][:2]) or "—"
    return f"- {'🔥 ' if x.get('hot') else ''}**{store}** [{x['title']}]({x['link']})" + (f" `{' '.join(tags)}`" if tags else "")


def build(items, since, site):
    cats = json.loads(STORES.read_text())["categories"]
    labels = {c["id"]: c["label"] for c in cats}
    labels["other"] = "その他(無料)"
    new = [x for x in items if x["firstSeen"] > since]
    hot = [x for x in new if x.get("hot")]
    now = dt.datetime.now(CT)
    title = f"お得情報 {now.month}/{now.day} 新着{len(new)}件(注目{len(hot)})"
    lines = [f"{MENTION} おはようございます。前回のまとめ以降の新着です。", ""]
    if site:
        lines += [f"一覧(絞り込み・期限順): {site}", ""]
    if not new:
        lines.append("新着はありませんでした。")
    if hot:
        lines += ["## 🔥 注目(無料・70%以上)", *[fmt_item(x) for x in hot[:15]], ""]
    for cid in [c["id"] for c in cats] + ["other"]:
        g = [x for x in new if cid in x["cats"] and not x.get("hot")]
        if not g:
            continue
        lines.append(f"## {labels[cid]}({len(g)})")
        lines += [fmt_item(x) for x in g[:MAX_PER_CAT]]
        if len(g) > MAX_PER_CAT:
            lines.append(f"- ほか {len(g) - MAX_PER_CAT} 件はサイトで")
        lines.append("")
    lines += ["---", "見出しとリンクは各ブログの RSS から自動で集めています。条件は必ずリンク先・お店の公式で確認してください。"]
    return title, "\n".join(lines), len(new)


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
    if a.dry_run:
        print(title)
        print(body)
        return

    try:
        api("POST", "/labels", {"name": LABEL, "color": "f9a825", "description": "毎朝のお得情報まとめ"})
    except Exception:  # noqa: BLE001  既にある
        pass
    for old in api("GET", f"/issues?labels={LABEL}&state=open&per_page=50") or []:
        api("PATCH", f"/issues/{old['number']}", {"state": "closed", "state_reason": "completed"})
    created = api("POST", "/issues", {"title": title, "body": body, "labels": [LABEL]})
    print(f"Issue #{created['number']} を作成(新着 {n} 件)")
    STATE.write_text(json.dumps({"lastSent": data["updated"], "lastDate": now_ct.date().isoformat(),
                                 "lastIssue": created["number"]}, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    sys.exit(main())
