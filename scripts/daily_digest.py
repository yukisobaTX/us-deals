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
MAX_LOCAL_CS = 10
MAX_LOCAL_HOU = 5
FAMILY_DAYS = 7
MAX_FAMILY_CS = 10
MAX_FAMILY_HOU = 4
MAX_HOU_FREE = 5
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


REGION_WORDS = ("ヒューストン", "ヒューストン広域", "ヒューストン各地", "カレッジステーション", "HS", "HS広域", "HS各地", "CS", "Houston", "College Station")


def abbr(t):
    """地名の略記(本人指定 10/27):カレッジステーション=CS、ヒューストン=HS。"""
    return (t or "").replace("カレッジステーション", "CS").replace("ヒューストン", "HS")


def clip(t, n):
    t = abbr(t).strip()
    return t if len(t) <= n else t[:n - 1] + "…"


KIND_ICON = {"公園・屋外": "🌳", "動物": "🦒", "エンタメ": "🎪", "スポーツ": "⚽", "子供向け": "🧒"}


def long_running(x):
    """2週間以上続く催し(展示・季節のパンプキンパッチなど)。"""
    d, e = x.get("date"), x.get("expires")
    return bool(d and e and e > d and (dt.date.fromisoformat(e) - dt.date.fromisoformat(d)).days >= 14)


def line(x, today, tomorrow, head=None):
    """メールの1行:「日付：何が(10文字以内)；どこで」。何がにリンク。お出かけ先は種類の絵文字を先頭に。"""
    sm = x.get("sum") or {}
    d = x.get("date")
    if not head and long_running(x):
        head = f"〜{md(x['expires'])}"
    when = head or ("今日" if d == today else "明日" if d == tomorrow else md(d) if d else "随時")
    icon = "".join(KIND_ICON[k] for k in (x.get("outing") or [])[:1])
    what = clip(sm.get("what") or sm.get("item") or x.get("ja") or x["title"], 10)
    where = sm.get("where") or sm.get("store") or "・".join(n for n in x.get("stores", [])[:1] if n != "レストラン全般")
    where = "" if where in REGION_WORDS else clip(where, 15)
    return f"- {when}：{icon}[{what}]({x['link']})" + (f"；{where}" if where else "")


def fmt_local(x, today):
    """地元・家族の催し:日時:[何のイベントか](リンク)(場所・費用)。要約がなければ日本語の見出し。"""
    sm = x.get("sum") or {}
    d = x.get("date")
    when = sm.get("when") or (md(d) if d else "日程は記事で")
    if d == today:
        when = "**今日** " + (when.split(" ", 1)[1] if " " in when else "")
    text = (sm.get("item") or x.get("ja") or x["title"]).strip()
    place = sm.get("store") or ""
    if place in ("ヒューストン", "ヒューストン広域", "カレッジステーション", "HS", "CS", "Houston", "College Station"):
        place = ""   # 見出し(カレッジステーション周辺/ヒューストン)と同じなら省く
    extra = "・".join(v for v in (place, sm.get("cond")) if v)
    return f"- {when.strip()}:[{text}]({x['link']})" + (f"({extra})" if extra else "")


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


# 体験・入場系の「無料」(公園・博物館の入場、教室、読み聞かせ、イベント参加など)。
# メールの無料欄は「食べ物・もらえる物」だけにする(本人指定 10/26)。サイトには残る。
EXPERIENCE_RE = re.compile(
    r"admission|entrance|entry\b|national parks?|\bparks?\b|museum|\bzoo\b|aquarium|"
    r"class(?:es)?\b|workshop|story ?time|lesson|tour\b|bowling|skating|concert|movie|"
    r"\bevents?\b|festival|webinar|seminar|"
    r"入場|入園|国立公園|公園|博物館|美術館|動物園|水族館|教室|クラス|ワークショップ|読み聞かせ|"
    r"ストーリータイム|体験|イベント|催し|ツアー|ボウリング|コンサート|映画", re.I)


DISCOUNT_RE = re.compile(r"\d+\s*%\s*off|\d+\s*%\s*オフ|割引", re.I)   # 割引は無料ではない


def is_goods(x):
    """食べ物・もらえる物か(体験・入場系でない)。"""
    sm = x.get("sum") or {}
    text = " ".join([x["title"], sm.get("item", ""), sm.get("what", "")])
    return not EXPERIENCE_RE.search(text) and not DISCOUNT_RE.search(text)


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
    # 📍地元(カレッジステーション優先・ヒューストン):今日・明日の分と、新着の今後の分(購入条件は問わない)
    # 👨‍👩‍👧 家族のお出かけ案:地元の家族・子供向けの催しで、今日から7日以内(日付なしは新着だけ)
    week = (today + dt.timedelta(days=FAMILY_DAYS)).isoformat()
    fam = [x for x in items if x.get("family") and not x.get("dup")
           and ((x.get("date") and t_iso <= x["date"] <= week) or (not x.get("date") and x["firstSeen"] > since))]
    # 日付の決まった催しを先に、長く続く展示などは後ろに
    fam_cs = sorted(by_date([x for x in fam if x["region"] == "College Station"]), key=long_running)[:MAX_FAMILY_CS]
    fam_hou = by_date([x for x in fam if x["region"] == "Houston"])[:MAX_FAMILY_HOU]
    fam_ids = {x["id"] for x in fam_cs + fam_hou}
    loc = [x for x in items if x.get("region") and not x.get("dup") and x["id"] not in fam_ids
           and (x.get("date") in (t_iso, tomorrow)
                or (x["firstSeen"] > since and (x.get("date") or "9999") >= t_iso))]
    loc_cs = by_date([x for x in loc if x["region"] == "College Station"])[:MAX_LOCAL_CS]
    loc_hou = by_date([x for x in loc if x["region"] == "Houston"])[:MAX_LOCAL_HOU]
    local_ids = {x["id"] for x in loc_cs + loc_hou}
    fbs = [x for x in fbs if x["id"] not in local_ids | fam_ids]
    # ヒューストンの無料情報は前半(カレッジステーション・全国)から外し、後半のヒューストン欄へ(本人指定 10/27)
    hou_fbs = [x for x in fbs if x.get("region") == "Houston"]
    fbs = [x for x in fbs if x.get("region") != "Houston"]
    near = [x for x in fbs if x.get("date") in (t_iso, tomorrow)
            or (not x.get("date") and x["firstSeen"] > since)]
    near = by_date([x for x in near if is_pure_free(x) and is_goods(x)])
    # この先:明後日〜2週間先の無料情報(短文のみ。毎朝の予定表として繰り返し載せる)
    later = by_date([x for x in fbs if x.get("date") and tomorrow < x["date"] <= horizon and is_goods(x)])[:MAX_LATER]
    hou_free = by_date([x for x in hou_fbs if is_goods(x) and (
        (x.get("date") and t_iso <= x["date"] <= horizon) or (not x.get("date") and x["firstSeen"] > since))])[:MAX_HOU_FREE]
    # 大型セール:前回のまとめ以降の記事を、セールごとに最大3件(短文のみ)
    ev_labels = {e["id"]: e["label"] for e in json.loads(STORES.read_text()).get("events", [])}
    ev_lines = []
    for eid, lab in ev_labels.items():
        g = sorted([x for x in items if x.get("event") == eid and x["firstSeen"] > since
                    and not x.get("freebie") and not x.get("dup")],
                   key=lambda x: x["posted"], reverse=True)
        ev_lines += [line(x, t_iso, tomorrow, head=f"【{lab}】") for x in g[:3]]
    n_hou = len(fam_hou) + len(loc_hou) + len(hou_free)
    n = len(near) + len(later) + len(ev_lines) + len(fam_cs) + len(loc_cs) + n_hou
    ln = lambda x: line(x, t_iso, tomorrow)
    # 件名:カレッジステーション(と全国)の件数を先に、ヒューストンは最後にまとめて
    parts = [f"今日・明日{len(near)}", *([f"家族{len(fam_cs)}"] if fam_cs else []),
             *([f"地元{len(loc_cs)}"] if loc_cs else []), *([f"今後{len(later)}"] if later else []),
             *([f"HS{n_hou}"] if n_hou else [])]
    title = f"お得ノート {today.month}/{today.day}:" + "/".join(parts)
    lines = [f"{MENTION} おはようございます。「日付：何が；どこで」で並べています(何がをタップで記事)。",
             *([f"一覧: {site}"] if site else []), "", "## 🎁 今日・明日(無料の食べ物・もらえる物、BOGO)"]
    lines += [ln(x) for x in near] or ["- 該当なし"]
    if fam_cs:
        lines += ["", "## 👨‍👩‍👧 家族のお出かけ(CS周辺・1週間。🌳公園 🦒動物 🎪エンタメ ⚽スポーツ 🧒子供)",
                  *[ln(x) for x in fam_cs]]
    if loc_cs:
        lines += ["", "## 📍 地元(CS周辺)", *[ln(x) for x in loc_cs]]
    if later or ev_lines:
        lines += ["", "## 📅 今後(詳細はサイト)", *[ln(x) for x in later]]
        if ev_lines:
            lines += ["", "**🛍 大型セール**", *ev_lines]
    if n_hou:
        lines += ["", "", "## 🏙 HS(お出かけ・遠出用)"]
        if fam_hou:
            lines += ["**👨‍👩‍👧 家族のお出かけ(1週間)**", *[ln(x) for x in fam_hou]]
        if loc_hou:
            lines += ["**📍 催し・地元情報**", *[ln(x) for x in loc_hou]]
        if hou_free:
            lines += ["**🎁 無料・BOGO(2週間)**", *[ln(x) for x in hou_free]]
    lines += ["", "---", "実施は店舗ごとに違うことがあります。リンク先・公式で確認してください。"]
    return title, "\n".join(lines), n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="時刻の判定をしない")
    ap.add_argument("--dry-run", action="store_true", help="Issue を作らず本文を表示")
    ap.add_argument("--test", action="store_true",
                    help="テスト送信:時刻を無視して GMAIL_USER だけに送る。件名に[テスト]、送信済みの記録は更新しない")
    a = ap.parse_args()
    if a.test:
        a.force = True
        os.environ["MAIL_TO"] = ""   # 追加の宛先には送らない

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
    if a.test:
        ok = mailer.send_mail("[テスト] " + title, body.replace(MENTION + " ", ""))
        print("テスト送信:" + ("送信しました(GMAIL_USER のみ)" if ok else "失敗"))
        return 0 if ok else 1
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
