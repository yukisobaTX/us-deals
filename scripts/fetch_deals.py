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
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
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


def parse_rss(text):
    """RSS 2.0 を読む。壊れた XML でも <item> 単位で拾えるだけ拾う。"""
    items = []
    try:
        root = ET.fromstring(text)
        nodes = root.iter("item")
        for it in nodes:
            items.append({
                "title": (it.findtext("title") or "").strip(),
                "link": (it.findtext("link") or "").strip(),
                "date": (it.findtext("pubDate") or "").strip(),
                "cats": [(c.text or "").strip() for c in it.findall("category") if c.text],
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
    return stores, types


FREE_RE = re.compile(r"(?<![A-Za-z])FREE(?![A-Za-z])(?!\s+(shipping|same[- ]day|pickup|delivery|returns?|trial|w/|with\b))", re.I)
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
    if not hit_stores and "free" not in tset:
        return None   # 対象の店でも無料でもないものは載せない
    if not hit_cats:
        hit_cats = ["other"]
    if not tset:
        tset.append("sale")
    return {"stores": hit_stores, "cats": hit_cats, "types": tset, "pct": pct, "price": price}


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
                "hot": ("free" in c["types"]) or (c["pct"] or 0) >= 50,
                **c,
            }
            added += 1
        stats[f["id"]] = {"read": len(raw_items), "added": added}

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


def parse_date_iso(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


if __name__ == "__main__":
    main()
