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


DESC = {}   # id → 本文冒頭(この実行の間だけ。deals.json には書かない)


def desc_text(h):
    """RSS の description の冒頭(地元記事の要約にだけ使う。保存はしない)。"""
    t = re.sub(r"<[^>]+>", " ", html.unescape(h or ""))
    t = re.sub(r"\[Read More[^\]]*\]|The post .* appeared first on .*", "", t)
    return re.sub(r"\s+", " ", t).strip()[:400]


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
                "desc": desc_text(it.findtext("description") or ""),
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
            "desc": desc_text(unc(tag("description"))),
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
    food = [w for cat in stores_cfg["categories"] if cat["id"] == "food" for s in cat["stores"] for w in s["keywords"]]
    FOOD_STORE[:] = [kw_regex(food)] if food else []
    other = [w for cat in stores_cfg["categories"] if cat["id"] != "food" for s in cat["stores"] for w in s["keywords"]]
    SHOP_STORE[:] = [kw_regex(other)] if other else []
    EVENTS[:] = [(e["id"], kw_regex(e["keywords"])) for e in stores_cfg.get("events", [])]
    return stores, types


EVENTS = []
FOOD_STORE = []   # レストラン・カフェの店名(BOGO を「もらえる」扱いにするかの判定)
SHOP_STORE = []   # スーパー・雑貨・通販の店名(ここでの BOGO は通常のセール扱い)
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


# ---------------- 地域(カレッジステーション・ヒューストン) ----------------
# 見出しに地名があれば地域の印を付ける(どの情報源でも)。地元の情報源(region 付き)はその地域。
REGION_KW = [
    ("College Station", re.compile(r"College Station|Bryan[- /]College Station|\bBCS\b|Brazos (?:Valley|County)|Aggieland|"
                                   r"Downtown Bryan|City of Bryan|Bryan,? (?:TX|Texas)|Navasota", re.I)),
    ("Houston", re.compile(r"Houston|\bKaty\b|Sugar Land|The Woodlands|Pearland|Galveston|Kemah|Cypress,? TX|"
                           r"\bConroe\b|Clear Lake|Baytown|League City|Friendswood|Tomball", re.I)),
]
# 地元ニュース局(WTAW など)は事件・スポーツが多いので、催し・無料・お得の見出しだけ拾う
LOCAL_EVENT_RE = re.compile(
    r"\bfree\b|festival|\bfair\b|parade|farmers'? market|market days|trunk[- ]or[- ]treat|halloween|"
    r"christmas|holiday|lights|tree lighting|fireworks|celebrat|giveaway|give away|giving away|grand opening|"
    r"open house|family|kids?\b|children|story ?time|library|concert|movie night|movies? in the park|"
    r"things to do|this weekend|events?\b|food drive|food truck|shred|recycl|hazardous|clean ?up|"
    r"museum|zoo|\bparks?\b|discount|deal", re.I)
LOCAL_NG_RE = re.compile(
    r"arrest|indict|charged|shoot|stabb|murder|kill|dead|death|dies|crash|police|sheriff|jail|theft|robbery|"
    r"assault|lawsuit|court|election|vote|voting|candidate|council|commission|\bbond\b|tax rate|"
    r"football|basketball|baseball|softball|volleyball|soccer|golf|equestrian|swim|track|tennis|\bSEC\b|"
    r"what we.re reading|writing contest|podcast|ribbon cutting|card sign-up|stream(?:ing)?\b|channel", re.I)


# 家族・子供向け(家族のお出かけ案)。地域の印がある記事だけに付ける
FAMILY_RE = re.compile(
    r"\bkids?\b|kid-friendly|children|child\b|famil(?:y|ies)|toddler|\bteens?\b|youth|story ?time|"
    r"trunk[- ]or[- ]tre|trick[- ]or[- ]treat|pumpkin|petting|\bzoo\b|aquarium|museum|santa|playground|splash pad|"
    r"\bcamps?\b|puppet|crafts?\b|lego|science|\bSTEM\b|book sale|hometown heroes|big rigs|touch[- ]a[- ]truck|"
    r"holiday lights|light show|parade|festival|\bfair\b|carnival|hayride|corn maze|farm", re.I)


def region_of(title):
    for name, rx in REGION_KW:
        if rx.search(title):
            return name
    return None


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
    r"|bogo\s+\d+\s*%|buy\s*(?:1|one),?\s*get\s*(?:1|one)\s*\d+\s*%"   # BOGO 50% Off は無料ではない
    r"|\bwin\b|enter now|sweepstakes|giveaway entry|instant win"
    r"|try (?:out )?.*for free|free trial|membership"
    r"|after (?:cash ?back|fetch|ibotta|rebate|walmart cash|.*rebate)|ibotta|fetch rewards|rebate"
    r"|for (?:veterans|military|active service|teachers|nurses|healthcare|first responders)"
    r"|veterans day"
    r"|\d+\s+free\s+months?|free\s+months?|audiobooks?|e-?books?|kindle|my new book|bonuses|earn free|ways to (?:earn|get)"
    r"|free printables?|free (?:download|webinar|course|class online)", re.I)
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


WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def local_date(title, posted):
    """地元の催しの日付:見出しの日付(10/30・Nov. 6)→ 曜日(Friday's など、掲載日以降の最初のその曜日)。"""
    d = event_date(title, posted)
    if d:
        return d
    m = re.search(r"\b(" + "|".join(WEEKDAYS) + r")(?:'s|’s)?\b", title, re.I)
    if m:
        ct = posted.astimezone(CT).date()
        wd = WEEKDAYS.index(m.group(1).lower())
        return (ct + dt.timedelta(days=(wd - ct.weekday()) % 7)).isoformat()
    return None


ROUNDUP_RE = re.compile(r"\bfreebies\b", re.I)   # 「Restaurant Deals & Freebies」などのまとめ記事
# 1つ買うと1つ無料(BOGO)。レストラン・カフェの飲食物だけを「もらえる」扱いにする(スーパーの BOGO は対象外)
BOGO_RE = re.compile(
    r"\bbogo\b|\bb1g1\b|buy\s*(?:1|one|a|any)\b.{0,40}?\bget\s*(?:1|one|a|another|second|2nd)\b.{0,30}?\bfree\b"
    r"|\b2[- ]for[- ]1\b|\btwo[- ]for[- ]one\b|free\s+(?:second|2nd)\b", re.I)
FOOD_WORD_RE = re.compile(
    r"coffee|latte|espresso|frappuccino|refresher|cold brew|\bdrinks?\b|\btea\b|boba|smoothie|lemonade|shake"
    r"|donuts?|doughnuts?|kolaches?|cookies?|cupcakes?|bagels?|pastr(?:y|ies)|croissants?|cinnamon rolls?|pretzels?"
    r"|burgers?|pizzas?|tacos?|burritos?|sandwich(?:es)?|subs?\b|footlongs?|wings|nuggets|fries|entr[eé]es?|meals?|bowls?"
    r"|ice cream|frosty|blizzard|custard|sundae", re.I)
# 「無料」の言い換え
FREE_ALT_RE = re.compile(r"on the house|complimentary|\bon us\b", re.I)


def is_food(title):
    """レストラン・カフェの飲食物か。スーパー・雑貨の店名だけがある見出しは除く。"""
    if any(rx.search(title) for rx in FOOD_STORE):
        return True
    if any(rx.search(title) for rx in SHOP_STORE):
        return False
    return bool(FOOD_WORD_RE.search(title))


def freebie_info(title, posted):
    """無料でもらえるものなら {"kind": "store"|"coupon", "when": 日付} を返す。"""
    if NOT_GIFT_RE.search(title) or ENDED_RE.search(title):
        return None
    if BOGO_RE.search(title):
        if not is_food(title):
            return None   # 飲食以外の BOGO(スーパー・雑貨)は通常のセール扱い
        kind = "store" if STORE_RE.search(title) else "coupon"
        return {"kind": kind, "when": event_date(title, posted), "bogo": True}
    if FREE_ALT_RE.search(title) and is_food(title):
        kind = "store" if STORE_RE.search(title) else "coupon"
        return {"kind": kind, "when": event_date(title, posted)}
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
            if it.get("desc"):
                DESC[iid] = it["desc"]   # 既にある記事も、配信に残っている間は要約の材料にする
            if iid in by_id:
                if it.get("thumb") and not by_id[iid].get("thumb"):
                    by_id[iid]["thumb"] = it["thumb"]   # 既存の記事にもサムネを補う
                continue
            posted = parse_date(it["date"]) or now
            if (now - posted).days > KEEP_DAYS:
                continue
            if f.get("localOnly") and (not LOCAL_EVENT_RE.search(title) or LOCAL_NG_RE.search(title)):
                continue   # 地元ニュース局は催し・無料・お得の見出しだけ
            c = classify(title, it["cats"], stores, types, stores_cfg.get("skipRegionsNotIn", []))
            if not c and f.get("region"):
                # 地元の情報源は、店名・無料の語がなくても催しとして載せる
                c = {"stores": [], "cats": ["other"], "types": ["sale"], "pct": None, "price": None,
                     "event": None, "eventNews": False}
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
        x["region"] = next((f["region"] for f in sources["feeds"] if f["name"] == x["source"] and f.get("region")), None) \
            or region_of(x["title"])
        if not x["region"]:
            x.pop("region")
        x["family"] = bool(x.get("region") and FAMILY_RE.search(x["title"]))
        if not x["family"]:
            x.pop("family")
        if x.get("region"):
            ld = local_date(x["title"], parse_date_iso(x["posted"]))
            if ld:
                x["localDate"] = ld
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
        free_todo = [x for x in by_id.values() if (x.get("freebie") or x.get("event")) and not x.get("region")
                     and (x.get("jaVia") != "gemini" or not (x.get("sum") or {}).get("what"))]
        # 朝のメールの「今日・明日」に載るもの(配布日が今日・明日)を先に、あとは新しい順
        _t = now.astimezone(CT).date()
        _soon = {_t.isoformat(), (_t + dt.timedelta(days=1)).isoformat()}
        free_todo.sort(key=lambda x: x["posted"], reverse=True)
        free_todo.sort(key=lambda x: ((x.get("freebie") or {}).get("when") or x.get("expires")) not in _soon)
        done = {}
        if gem and free_todo and usage["count"] < 15:
            usage["count"] += 1
            for k, v in tj.gemini_once(rows(free_todo[:25])).items():
                done[k] = (v, "gemini")
            usage_p.write_text(json.dumps(usage) + "\n")
        # 地元・家族の記事 → 「何のイベントか・場所・日時・費用」に要約(家族向け・日付の近いものから)
        ev_todo = [x for x in by_id.values() if x.get("region")
                   and (x.get("jaVia") != "gemini-ev" or not (x.get("sum") or {}).get("what"))]
        ev_todo.sort(key=lambda x: (not x.get("family"), x.get("localDate") or "9999", x["posted"]))
        if gem and ev_todo and usage.get("ev", 0) < 5 and usage["count"] < 19:
            usage["count"] += 1
            usage["ev"] = usage.get("ev", 0) + 1
            ev_rows = [(i, d, t, DESC.get(i, "")) for i, d, t in rows(ev_todo[:25])]
            for k, v in tj.gemini_once(ev_rows, tj.EV_PROMPT).items():
                done[k] = (v, "gemini-ev")
            usage_p.write_text(json.dumps(usage) + "\n")
        need_mt = [x for x in free_todo if x["id"] not in done and not x.get("ja")]
        # 地元・家族の催しを先に訳す(朝のメールに載るため)。あとは新しい順
        rest = sorted([x for x in by_id.values() if not x.get("freebie") and not x.get("ja")],
                      key=lambda x: x["posted"], reverse=True)
        need_mt += [x for x in rest if x.get("region")] + [x for x in rest if not x.get("region")]
        for k, v in tj.mymemory_many(rows(need_mt), limit=25).items():
            done[k] = (v, "mymemory")
        for x in by_id.values():
            if x["id"] in done:
                v, how = done[x["id"]]
                if isinstance(v, dict):
                    # 空の項目は前の要約を残す(what・where だけ返ってきた場合など)
                    v = {**(x.get("sum") or {}), **{k2: v2 for k2, v2 in v.items() if v2}}
                    x["sum"], x["ja"] = v, v.get("item") or x.get("ja") or x["title"]
                else:
                    x["ja"] = v
                    x.pop("sum", None)
                x["jaVia"] = how
        stats["ja"] = {"gemini": sum(1 for v in done.values() if v[1] == "gemini"),
                       "geminiEvent": sum(1 for v in done.values() if v[1] == "gemini-ev"),
                       "mymemory": sum(1 for v in done.values() if v[1] == "mymemory"),
                       "geminiToday": usage["count"], "model": tj.GEMINI_MODEL,
                       **{f"{k}Error": v[:300] for k, v in tj.LAST_ERROR.items()}}

    # 「店舗名:もらえるもの:日時:条件」の形に(Gemini 以外は分かる範囲で組み立てる)
    for x in by_id.values():
        if x.get("jaVia") in ("gemini", "gemini-ev"):
            continue
        if x.get("region"):
            ld = x.get("localDate")
            x["sum"] = {"store": "", "item": x.get("ja") or x["title"],
                        "when": f"{int(ld[5:7])}/{int(ld[8:10])}({WD[dt.date.fromisoformat(ld).weekday()]})" if ld else "",
                        "cond": ""}
        else:
            x["sum"] = fallback_sum(x)

    # 別の情報源の同じ話題(例:Tiff's Treats の無料アイス)を重複として印を付ける(先に見つけた方を残す)
    mark_duplicates(by_id.values())

    # 並べ替え用の日付:無料の配布日 → 要約の日時(M/D) → 期限
    for x in by_id.values():
        x["date"] = sort_date(x)

    # 古いもの・期限切れを削除
    keep = []
    today_ct = now.astimezone(CT).date().isoformat()
    local_only = {f["name"] for f in sources["feeds"] if f.get("localOnly")}
    for x in by_id.values():
        posted = parse_date_iso(x["posted"])
        if (now - posted).days > KEEP_DAYS:
            continue
        if x["source"] in local_only and LOCAL_NG_RE.search(x["title"]):
            continue   # 除外の語を後から足したときも、既にある記事から外す
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


STOP = {"free", "the", "a", "an", "and", "or", "for", "at", "on", "with", "of", "to", "in", "get", "score",
        "your", "this", "today", "only", "just", "new", "&", "+", "-", "|", "–"}


def _tokens(t):
    return {w for w in re.findall(r"[a-z0-9’']+", t.lower()) if w not in STOP and len(w) > 2}


def mark_duplicates(items):
    items = sorted(items, key=lambda x: x["firstSeen"])
    kept = []
    for x in items:
        x.pop("dup", None)
        tx = _tokens(x["title"])
        for y in kept:
            if y["source"].split("(")[0] == x["source"].split("(")[0]:
                continue
            ty = y["_t"]
            if tx and ty and len(tx & ty) / len(tx | ty) >= 0.45:
                x["dup"] = y["id"]
                break
        if "dup" not in x:
            x["_t"] = tx
            kept.append(x)
    for x in items:
        x.pop("_t", None)


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
    return x.get("localDate") or x.get("expires")


def parse_date_iso(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


if __name__ == "__main__":
    main()
