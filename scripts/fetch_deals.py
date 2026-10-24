#!/usr/bin/env python3
"""お得情報の収集(AI なし・標準ライブラリのみ)。

RSS を取得 → 店・種類で分類 → public/data/deals.json に追記・整理する。
保存するのは見出し・リンク・掲載日・分類だけ(本文は保存しない)。

使い方:
  python3 scripts/fetch_deals.py              # 取得して保存
  python3 scripts/fetch_deals.py --dry-run    # 取得して件数だけ表示
  python3 scripts/fetch_deals.py --from-dir tests/fixtures   # ネットに出ずにファイルから読む(試験用)
"""
import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
OUT = ROOT / "public" / "data" / "deals.json"
UA = "us-deals-personal/1.0 (+personal RSS reader; github.com/yukisobaTX)"
KEEP_DAYS = 21          # これより古い記事は削除
DEFAULT_LIFE_DAYS = 7   # 期限が読み取れない記事の目安(掲載日から)


# ---------------- 取得 ----------------
def fetch(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.5"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def page_url(url, n):
    if n == 1:
        return url
    return url + ("&" if "?" in url else "?") + f"paged={n}"


IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)


def find_thumb(it_xml_get):
    """サムネイル画像の URL(画像そのものは保存しない)。"""
    for t in it_xml_get:
        if t and t.startswith("https://"):
            return t.strip()
    return None


def parse_rss(text):
    """RSS 2.0 を読む。壊れた XML でも <item> 単位で拾えるだけ拾う。"""
    items = []
    try:
        root = ET.fromstring(text)
        nodes = root.iter("item")
        ns_media = "{http://search.yahoo.com/mrss/}"
        ns_content = "{http://purl.org/rss/1.0/modules/content/}encoded"
        for it in nodes:
            html_parts = (it.findtext(ns_content) or "") + (it.findtext("description") or "")
            m = IMG_RE.search(html_parts)
            mt = it.find(ns_media + "thumbnail") if it.find(ns_media + "thumbnail") is not None else it.find(ns_media + "content")
            items.append({
                "title": (it.findtext("title") or "").strip(),
                "link": (it.findtext("link") or "").strip(),
                "date": (it.findtext("pubDate") or "").strip(),
                "cats": [(c.text or "").strip() for c in it.findall("category") if c.text],
                "thumb": find_thumb([(it.findtext("thumbnail-image") or "").strip(),
                                     mt.get("url") if mt is not None else None,
                                     m.group(1) if m else None]),
            })
        return items
    except ET.ParseError:
        pass
    for block in re.findall(r"<item\b.*?</item>", text, flags=re.S):
        def tag(name):
            m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", block, flags=re.S)
            return m.group(1) if m else ""
        def unc(s):
            return re.sub(r"^<!\[CDATA\[(.*)\]\]>$", r"\1", s.strip(), flags=re.S)
        items.append({
            "title": unc(tag("title")),
            "link": unc(tag("link")),
            "date": unc(tag("pubDate")),
            "cats": [unc(c) for c in re.findall(r"<category[^>]*>(.*?)</category>", block, flags=re.S)],
            "thumb": find_thumb([unc(tag("thumbnail-image")),
                                 (IMG_RE.search(html.unescape(block)) or [None, None])[1]]),
        })
    return items


# ---------------- 分類 ----------------
def kw_regex(words):
    parts = []
    for w in words:
        e = re.escape(w).replace(r"\'", "['’]")
        parts.append(rf"(?<![A-Za-z0-9]){e}(?![A-Za-z0-9])")
    return re.compile("|".join(parts), re.I)


def build_matchers(stores_cfg):
    stores = []
    for cat in stores_cfg["categories"]:
        for s in cat["stores"]:
            stores.append((cat["id"], s["name"], kw_regex(s["keywords"])))
    types = [(t["id"], kw_regex(t["keywords"])) for t in stores_cfg["types"] if t["id"] != "free"]
    EVENTS[:] = [(e["id"], kw_regex(e["keywords"])) for e in stores_cfg.get("events", [])]
    return stores, types


EVENTS = []
# 大型セールの「日程発表・開始・チラシ公開」記事(即時通知の対象)
EVENT_NEWS_RE = re.compile(
    r"announc|dates?\b|starts?|kicks? off|is (?:now )?live|now live|early access|ad scan|ad leak|leaked|"
    r"\bad\b.*(?:released|is here|out)|preview|sneak peek|begins?|coming|countdown|when is", re.I)


def event_of(title):
    for eid, rx in EVENTS:
        if rx.search(title):
            return eid
    return None


FREE_RE = re.compile(r"(?<![A-Za-z])FREE(?![A-Za-z])(?!\s+(shipping|same[- ]day|pickup|delivery|returns?|trial|w/|with\b|people\b))", re.I)
ENDED_RE = re.compile(r"has ended|offer ended|expired", re.I)
FREE_CAT_RE = re.compile(r"freebie", re.I)
PCT_RE = re.compile(r"(\d{2})\s*%\s*off", re.I)
PRICE_RE = re.compile(r"\$(\d+(?:\.\d{1,2})?)")
REG_RE = re.compile(r"\(\s*reg\.?\s*\$(\d+(?:\.\d{1,2})?)", re.I)
REGION_RE = re.compile(r"^\s*\[([^\]]+)\]")
TODAY_RE = re.compile(r"today only|1[- ]day only|ends tonight|today \(\d", re.I)
UNTIL_RE = re.compile(r"(?:thru|through|until|ends?|by|valid (?:thru|through)?)\s+(\d{1,2})/(\d{1,2})", re.I)


def classify(title, cats, stores, types, skip_regions):
    text = title + " | " + " | ".join(cats)
    # 地域限定(Doctor of Credit の [MA, NH] など)で、テキサス・全国でないものは除外
    m = REGION_RE.match(title)
    if m and not any(r.lower() in m.group(1).lower() for r in skip_regions):
        return None
    hit_stores, hit_cats = [], []
    for cid, name, rx in stores:
        if rx.search(text):
            if name not in hit_stores:
                hit_stores.append(name)
            if cid not in hit_cats:
                hit_cats.append(cid)
    tset = []
    if FREE_RE.search(title) or any(FREE_CAT_RE.search(c) for c in cats):
        tset.append("free")
    for tid, rx in types:
        if rx.search(title):
            tset.append(tid)
    pct = None
    m = PCT_RE.search(title)
    if m:
        pct = int(m.group(1))
    reg = REG_RE.search(title)
    prices = [float(p) for p in PRICE_RE.findall(title)]
    price = None
    if reg and prices:
        regv = float(reg.group(1))
        cand = [p for p in prices if p < regv]
        if cand:
            price = min(cand)
            calc = round((1 - price / regv) * 100)
            pct = max(pct or 0, calc)
    if len(hit_stores) > 1 and "レストラン全般" in hit_stores:
        hit_stores.remove("レストラン全般")
    if ENDED_RE.search(title):
        return None
    ev = event_of(title)
    if not hit_stores and "free" not in tset and not ev:
        return None   # 対象の店でも無料でも大型セールでもないものは載せない
    if not hit_cats:
        hit_cats = ["other"]
    if not tset:
        tset.append("sale")
    return {"stores": hit_stores, "cats": hit_cats, "types": tset, "pct": pct, "price": price,
            "event": ev, "eventNews": bool(ev and EVENT_NEWS_RE.search(title))}


# ---------------- 無料でもらえるもの(ギフト・店頭配布) ----------------
GIFT_FREE_RE = re.compile(r"(?<![A-Za-z-])FREE(?![A-Za-z-])", re.I)
# 「無料」でも、もらえる物ではないもの(送料・受け取り・アプリ・〜フリー製品 など)
NOT_GIFT_RE = re.compile(
    r"free\s+(?:[\w'’-]+\s+){0,2}(?:shipping|delivery|pickup|returns?)\b"
    r"|free\s+\w+\s+app\b|better than free|free or cheap|print this free"
    r"|buy\s*(?:1|one),?\s*get\s*(?:1|one)\s*free|bogo|b1g1"
    r"|\bwin\b|enter now|sweepstakes|giveaway entry|instant win"
    r"|try (?:out )?.*for free|free trial|membership"
    r"|after (?:cash ?back|fetch|ibotta|rebate|walmart cash|.*rebate)|ibotta|fetch rewards|rebate"
    r"|for (?:veterans|military|active service|teachers|nurses|healthcare|first responders)"
    r"|veterans day", re.I)
STORE_RE = re.compile(
    r"\bevent\b|workshop|in[- ]store|today\b|this weekend|tonight|get there early|first [\d,]+"
    r"|@ ?\d|\b\d{1,2}(?::\d\d)? ?(?:am|pm)\b|\bon \d{1,2}/\d{1,2}|\bon (?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* \d"
    r"|photos? with santa|haircut|while supplies last|plushie|\bat (?:target|lowe'?s|home depot|walmart|macy'?s|petco|petsmart|tractor supply|bass pro|barnes|kroger|h-e-b|heb)\b",
    re.I)
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def event_date(title, posted):
    """見出しから「いつもらえるか」を読む(開始日)。読めなければ None。"""
    ct = posted.astimezone(CT).date()
    if re.search(r"\btoday\b|tonight|today only", title, re.I):
        return ct.isoformat()
    if re.search(r"this weekend", title, re.I):
        return (ct + dt.timedelta(days=max(0, 5 - ct.weekday()))).isoformat()
    m = re.search(r"(\d{1,2})/(\d{1,2})", title)
    mo = d = None
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
    else:
        m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? (\d{1,2})(?:st|nd|rd|th)?\b", title, re.I)
        if m:
            mo, d = MONTHS[m.group(1).lower()], int(m.group(2))
    if not mo:
        return None
    y = ct.year + (1 if mo < ct.month - 6 else 0)
    try:
        return dt.date(y, mo, d).isoformat()
    except ValueError:
        return None


ROUNDUP_RE = re.compile(r"\bfreebies\b", re.I)   # 「Restaurant Deals & Freebies」などのまとめ記事


def freebie_info(title, posted):
    """無料でもらえるものなら {"kind": "store"|"coupon", "when": 日付} を返す。"""
    if NOT_GIFT_RE.search(title) or ENDED_RE.search(title):
        return None
    if not GIFT_FREE_RE.search(title):
        if ROUNDUP_RE.search(title):
            return {"kind": "coupon", "when": event_date(title, posted), "roundup": True}
        return None
    kind = "store" if STORE_RE.search(title) else "coupon"
    return {"kind": kind, "when": event_date(title, posted)}


def parse_date(s):
    try:
        d = email.utils.parsedate_to_datetime(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def guess_expiry(title, posted):
    """見出しから期限を推定する。読めなければ None(画面では掲載日+7日を目安にする)。"""
    ct = posted.astimezone(CT)
    if TODAY_RE.search(title):
        return ct.date().isoformat()
    m = UNTIL_RE.search(title)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        y = ct.year + (1 if mo < ct.month - 6 else 0)
        try:
            return dt.date(y, mo, d).isoformat()
        except ValueError:
            return None
    return None


# ---------------- 本体 ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--from-dir", help="feed id ごとの XML(<id>.xml)を読む。試験用")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--no-translate", action="store_true", help="日本語化しない(試験用)")
    a = ap.parse_args()

    sources = json.loads((CONFIG / "sources.json").read_text())
    stores_cfg = json.loads((CONFIG / "stores.json").read_text())
    stores, types = build_matchers(stores_cfg)
    out = Path(a.out)
    db = json.loads(out.read_text()) if out.exists() else {"items": []}
    by_id = {x["id"]: x for x in db.get("items", [])}
    now = dt.datetime.now(dt.timezone.utc)
    errors, stats = [], {}

    for f in sources["feeds"]:
        raw_items = []
        for n in range(1, f.get("pages", 1) + 1):
            try:
                if a.from_dir:
                    p = Path(a.from_dir) / f"{f['id']}.xml"
                    text = p.read_text() if (n == 1 and p.exists()) else ""
                else:
                    text = fetch(page_url(f["url"], n))
                    time.sleep(2)   # 相手に負担をかけない
            except Exception as e:  # noqa: BLE001
                if n == 1:
                    errors.append(f"{f['name']}: {e}")
                break
            got = parse_rss(text) if text else []
            if not got:
                break
            raw_items += got
        added = 0
        excl = {c.lower() for c in f.get("excludeCategories", [])}
        for it in raw_items:
            title = html.unescape(re.sub(r"<[^>]+>", "", it["title"])).strip()
            link = it["link"].strip()
            if not title or not link.startswith("http"):
                continue
            if excl and any(c.lower() in excl for c in it["cats"]):
                continue
            iid = hashlib.sha1(link.split("?")[0].rstrip("/").encode()).hexdigest()[:12]
            if iid in by_id:
                if it.get("thumb") and not by_id[iid].get("thumb"):
                    by_id[iid]["thumb"] = it["thumb"]   # 既存の記事にもサムネを補う
                continue
            posted = parse_date(it["date"]) or now
            if (now - posted).days > KEEP_DAYS:
                continue
            c = classify(title, it["cats"], stores, types, stores_cfg.get("skipRegionsNotIn", []))
            if not c:
                continue
            by_id[iid] = {
                "id": iid, "title": title, "link": link, "source": f["name"],
                "posted": posted.isoformat(timespec="minutes").replace("+00:00", "Z"),
                "firstSeen": now.isoformat(timespec="minutes").replace("+00:00", "Z"),
                "expires": guess_expiry(title, posted),
                "thumb": it.get("thumb"),
                **({"noAlert": True} if f.get("alert") is False else {}),
                **({"region": f["region"]} if f.get("region") else {}),
                "hot": ("free" in c["types"]) or (c["pct"] or 0) >= 70,
                **c,
            }
            added += 1
        stats[f["id"]] = {"read": len(raw_items), "added": added}

    # 無料判定・大型セール判定は毎回すべての記事にかけ直す(ルール変更を過去分にも反映)
    for x in by_id.values():
        x["event"] = event_of(x["title"])
        x["eventNews"] = bool(x["event"] and EVENT_NEWS_RE.search(x["title"]))
        x["freebie"] = freebie_info(x["title"], parse_date_iso(x["posted"]))
        if x["freebie"] and x["freebie"]["when"] and not x.get("expires") and x["freebie"]["kind"] == "store":
            x["expires"] = x["freebie"]["when"]

    # 日本語化:
    # - 無料でもらえるもの → Gemini で4項目に要約(無料枠は1日20回なので、1回の実行で最大1回・1日15回まで)
    #   Gemini が使えないときは MyMemory の機械翻訳(次の回にまた Gemini を試す)
    # - セール記事 → MyMemory の機械翻訳(1回20件まで、新しい順)
    if not (a.no_translate or a.from_dir):
        import translate_ja as tj
        gem = bool(os.environ.get("GEMINI_API_KEY"))
        usage_p = OUT.parent / "gemini-usage.json"
        today = now.astimezone(CT).date().isoformat()
        usage = json.loads(usage_p.read_text()) if usage_p.exists() else {}
        if usage.get("date") != today:
            usage = {"date": today, "count": 0}
        rows = lambda xs: [(x["id"], parse_date_iso(x["posted"]).astimezone(CT).strftime("%Y-%m-%d"), x["title"]) for x in xs]
        free_todo = [x for x in by_id.values() if (x.get("freebie") or x.get("eventNews")) and x.get("jaVia") != "gemini"]
        free_todo.sort(key=lambda x: x["posted"], reverse=True)
        done = {}
        if gem and free_todo and usage["count"] < 15:
            usage["count"] += 1
            for k, v in tj.gemini_once(rows(free_todo[:25])).items():
                done[k] = (v, "gemini")
            usage_p.write_text(json.dumps(usage) + "\n")
        need_mt = [x for x in free_todo if x["id"] not in done and not x.get("ja")]
        need_mt += sorted([x for x in by_id.values() if not x.get("freebie") and not x.get("ja")],
                          key=lambda x: x["posted"], reverse=True)
        for k, v in tj.mymemory_many(rows(need_mt), limit=25).items():
            done[k] = (v, "mymemory")
        for x in by_id.values():
            if x["id"] in done:
                v, how = done[x["id"]]
                if isinstance(v, dict):
                    x["sum"], x["ja"] = v, v["item"]
                else:
                    x["ja"] = v
                    x.pop("sum", None)
                x["jaVia"] = how
        stats["ja"] = {"gemini": sum(1 for v in done.values() if v[1] == "gemini"),
                       "mymemory": sum(1 for v in done.values() if v[1] == "mymemory"),
                       "geminiToday": usage["count"], "model": tj.GEMINI_MODEL,
                       **{f"{k}Error": v[:300] for k, v in tj.LAST_ERROR.items()}}

    # 「店舗名:もらえるもの:日時:条件」の形に(Gemini 以外は分かる範囲で組み立てる)
    for x in by_id.values():
        if x.get("jaVia") != "gemini":
            x["sum"] = fallback_sum(x)

    # 並べ替え用の日付:無料の配布日 → 要約の日時(M/D) → 期限
    for x in by_id.values():
        x["date"] = sort_date(x)

    # 古いもの・期限切れを削除
    keep = []
    today_ct = now.astimezone(CT).date().isoformat()
    for x in by_id.values():
        posted = parse_date_iso(x["posted"])
        if (now - posted).days > KEEP_DAYS:
            continue
        if x.get("expires") and x["expires"] < (dt.date.fromisoformat(today_ct) - dt.timedelta(days=2)).isoformat():
            continue
        keep.append(x)
    keep.sort(key=lambda x: x["posted"], reverse=True)
    result = {"updated": now.isoformat(timespec="minutes").replace("+00:00", "Z"),
              "count": len(keep), "stats": stats, "errors": errors, "items": keep}

    print(json.dumps({"count": len(keep), "stats": stats, "errors": errors}, ensure_ascii=False))
    if not a.dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    # すべての取得先が失敗したときだけ異常終了(1つの失敗では止めない)
    if errors and len(errors) == len(sources["feeds"]):
        sys.exit(1)


WD = "月火水木金土日"
COND_RULES = [
    (r"rewards? members?|members? only|\bmembers\b", "会員限定"), (r"w/ (?:any )?purchase|with (?:any )?purchase|\bw/ .*meal|with any .*meal", "購入時"),
    (r"first ([\d,]+)", "先着{0}名"), (r"register|rsvp|sign up", "要登録"), (r"promo code|code\b", "コード入力"),
    (r"\bapp\b", "アプリ"), (r"while supplies last|get there early", "なくなり次第終了"), (r"kids?\b", "子ども向け"),
]


def fallback_sum(x):
    """Gemini がないとき:店・日時・条件は見出しから機械的に、もらえるものは翻訳文。"""
    store = "・".join(n for n in x.get("stores", [])[:2] if n != "レストラン全般")
    if not store:   # 「at Petco」「with Jimmy John’s ...」の大文字の語を店名とみなす(at を優先)
        for kw in ("at", "with"):
            m = re.search(rf"\b{kw}\s+((?:[A-Z][\w'’&.-]*(?:\s+(?:&|and)\s+|\s+)?){{1,4}})", x["title"])
            if not m:
                continue
            cand = re.sub(r"\s+(?:Triple|Kids|Holiday|Any|Today|On|January|February|March|April|May|June|July|"
                          r"August|September|October|November|December)\b.*$", "", m.group(1)).strip(" &")
            if cand and cand.split()[0] not in ("Santa", "Noon", "Purchase", "Any", "Free", "FREE"):
                store = cand
                break
    when = ""
    fb = x.get("freebie") or {}
    d = fb.get("when") or x.get("expires")
    if d:
        dd = dt.date.fromisoformat(d)
        when = f"{dd.month}/{dd.day}({WD[dd.weekday()]})" + ("" if fb.get("when") else "まで")
        m = re.search(r"(\d{1,2})(?::(\d\d))?\s*-\s*(\d{1,2})(?::\d\d)?\s*(am|pm)|@ ?(\d{1,2})(?::(\d\d))? ?(am|pm)|(\d{1,2})(?::(\d\d))? ?(am|pm)", x["title"], re.I)
        if m:
            when += " " + m.group(0).replace(" ", "").replace("@", "")
    conds = []
    for rx, lab in COND_RULES:
        m = re.search(rx, x["title"], re.I)
        if m:
            lab = lab.format(*m.groups()) if m.groups() else lab
            if lab not in conds:
                conds.append(lab)
    return {"store": store, "item": x.get("ja") or "", "when": when, "cond": "・".join(conds[:3])}


def sort_date(x):
    fb = x.get("freebie") or {}
    if fb.get("when"):
        return fb["when"]
    w = (x.get("sum") or {}).get("when") or ""
    m = re.search(r"(\d{1,2})/(\d{1,2})", w)
    if m:
        posted = parse_date_iso(x["posted"]).astimezone(CT).date()
        mo, d = int(m.group(1)), int(m.group(2))
        y = posted.year + (1 if mo < posted.month - 6 else 0)
        try:
            return dt.date(y, mo, d).isoformat()
        except ValueError:
            pass
    return x.get("expires")


def parse_date_iso(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


if __name__ == "__main__":
    main()
