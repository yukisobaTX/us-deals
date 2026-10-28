#!/usr/bin/env python3
"""分類ルールの試験(ネット不要)。python3 tests/test_classify.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fetch_deals as f  # noqa: E402

cfg = json.loads((ROOT / "config" / "stores.json").read_text())
stores, types = f.build_matchers(cfg)
skip = cfg["skipRegionsNotIn"]


def c(title, cats=()):
    return f.classify(title, list(cats), stores, types, skip)


CASES = [
    # (見出し, カテゴリ, 期待)
    ("Ghost Decor Just $14.99 on Amazon (Reg. $35)", [], lambda r: r["stores"] == ["Amazon"] and r["pct"] == 57),
    ("FREE Sample at Target", [], lambda r: "free" in r["types"] and r["cats"] == ["home"]),
    ("Socks w/ FREE Shipping at Walmart", [], lambda r: "free" not in r["types"]),
    ("Score 6 FREE Photo Cards w/ Same Day Pickup", ["Walgreens", "Legit Freebies & Samples"], lambda r: "free" in r["types"]),
    ("BOGO Drinks at Starbucks", ["Restaurant Deals"], lambda r: r["stores"] == ["Starbucks"] and "bogo" in r["types"]),
    ("[Texas Area] H-E-B: Get $10 GC with $50 Purchase", [], lambda r: r["stores"] == ["H-E-B"] and "gc" in r["types"]),
    ("[MA, NH] Some Bank $750 Bonus", [], lambda r: r is None),
    ("Random Gadget 30% Off", ["Deals"], lambda r: r is None),
    ("Lowe's 50% Off Mums", [], lambda r: r["stores"] == ["Lowe's"] and r["pct"] == 50),
    ("Up to 75% Off Free People + Free Shipping", [], lambda r: r is None),
    ("Urban Air FREE Pass Offer Has Ended", [], lambda r: r is None),
    ("Black Friday 2026 Ad Scan Is Here!", [], lambda r: r["event"] == "black-friday" and r["eventNews"]),
    ("Amazon Prime Day 2027 Dates Announced", [], lambda r: r["event"] == "prime-day" and r["eventNews"]),
    ("Best Early Black Friday TV Deals", [], lambda r: r["event"] == "black-friday" and not r["eventNews"]),
    ("Texas Tax-Free Weekend Starts Friday", [], lambda r: r["event"] == "tax-free" and r["eventNews"]),
    ("Weee! $20 Off First Order", [], lambda r: r["stores"] == ["Weee!"]),
]

import datetime as dt  # noqa: E402
P = dt.datetime(2026, 10, 24, 15, tzinfo=dt.timezone.utc)
FREEBIES = [
    ("FREE Gold Lightning McQueen Car Toy at Macy's (Today @ 4 PM)", "store", "2026-10-24"),
    ("FREE Home Depot Kids Workshop on 11/7 | Register Now", "store", "2026-11-07"),
    ("FREE Pet Photos with Santa at Petco on December 12th", "store", "2026-12-12"),
    ("Free LEGO Holiday Build Event at Barnes & Noble November 13-15", "store", "2026-11-13"),
    ("RUN! FREE Dunkin' Coffee Promo Code Just Dropped", "coupon", None),
    ("Get a FREE Entree w/ Purchase at QDOBA 10/31 and 11/1", "coupon", "2026-10-31"),
    ("Diet Coke Caffeine-Free 12-Pack Just $4.45 Shipped on Amazon", None, None),
    ("Socks Only $2.99 + Free CVS Pickup", None, None),
    ("Buy 1, Get 1 FREE Oscar Mayer Hot Dogs After Walmart Cash", None, None),
    ("TWO FREE Downy Sprays After Cash Back at Walmart", None, None),
    ("Win a $100 Starbucks Gift Card - Enter Now", None, None),
    ("Try Out 3 Months of SiriusXM for FREE", None, None),
    ("FREE Great Clips Haircuts for Veterans & Active Service Members on November 11th", None, None),
    ("Subway BOGO FREE Footlongs Coming October 27th", "coupon", "2026-10-27"),
    ("Buy One, Get One FREE Starbucks Drinks Today Only", "store", "2026-10-24"),
    ("Dutch Bros BOGO Drinks on 10/30 for Rewards Members", "store", "2026-10-30"),
    ("Krispy Kreme: Buy a Dozen, Get a Second Dozen FREE", "coupon", None),
    ("BOGO 50% Off Favorite Day Halloween Snacks at Target", None, None),
    ("This Week's Kroger BOGO Deals = Savings on Halloween Candy", None, None),
    ("Buy 1 Get 1 FREE Tide Pods at CVS", None, None),
    ("Buy 1 Get 1 FREE Gatorade Drinks at Walmart", None, None),
    ("Complimentary Coffee at Shipley Donuts This Weekend", "store", "2026-10-24"),
    ("NEW Walmart Promo Codes: $10 Off + Free Express Delivery", None, None),
    ("Best Halloween Restaurant Deals & Freebies", "coupon", None),
    ("Sirius XM Deal: 3 FREE Months of XM Radio", None, None),
    ("10 Ways to Listen to the Audiobooks for Free (or Almost Free!)", None, None),
    ("My new book + $75 in FREE bonuses", None, None),
    ("Get a FREE Monster Taco & Small Drink at Jack in the Box Today!", "store", "2026-10-24"),
    ("Veterans Day 2026 Offers: FREE Meals, Haircuts & More", None, None),
]
bad = 0
a = {"id": "a", "title": "FREE Tiff’s Treats Ice Cream Sandwiches for Young Athletes This Weekend", "source": "Hip2Save", "firstSeen": "1"}
b = {"id": "b", "title": "Tiff’s Treats: FREE Ice Cream Sandwiches for Young Athletes on October 24th", "source": "Money Saving Mom", "firstSeen": "2"}
c2 = {"id": "c", "title": "FREE Pet Photos with Santa at Petco", "source": "Money Saving Mom", "firstSeen": "3"}
f.mark_duplicates([a, b, c2])
if b.get("dup") != "a" or a.get("dup") or c2.get("dup"):
    bad += 1
    print("NG dup", a, b, c2)
for title, kind, when in FREEBIES:
    r = f.freebie_info(title, P)
    if r and "BOGO" in title.upper() and not r.get("bogo") and "50%" not in title:
        bad += 1
        print("NG bogo flag", title, r)
    got = (r["kind"], r["when"]) if r else (None, None)
    if got[0] != kind or (kind and got[1] != when):
        bad += 1
        print("NG freebie", title, r)

for title, cats, ok in CASES:
    r = c(title, cats)
    try:
        good = ok(r)
    except Exception:  # noqa: BLE001
        good = False
    if not good:
        bad += 1
        print("NG", title, r)
# 地域(2026-10-26):地名で印を付ける/地元ニュース局は催し・無料だけ
REGIONS = [("FREE Kolache Day in College Station", "College Station"), ("Houston Zoo Free Day", "Houston"),
           ("Bryan-College Station Holiday Lights", "College Station"), ("Bryan Cranston new movie", None),
           ("Free Pancakes at IHOP", None)]
for title, want in REGIONS:
    if f.region_of(title) != want:
        bad += 1
        print("NG region", title, f.region_of(title))
LOCAL = [("It's Hazardous Household Waste Weekend!", True), ("Two Arrested For Shoplifting at Walmart", False),
         ("Aggie Football Drops 31-20 Battle to Alabama", False), ("Downtown Bryan Holiday Parade returns", True)]
for title, want in LOCAL:
    got = bool(f.LOCAL_EVENT_RE.search(title)) and not f.LOCAL_NG_RE.search(title)
    if got != want:
        bad += 1
        print("NG local", title, got)
# 家族のお出かけ(2026-10-26):家族・子供向けの判定と、催しの日付(曜日・月名)
import datetime as _dt
FAM = [("Trunk or Tree-t at Wolf Pen Creek", True), ("Friends of the Library Fall Book Sale", True),
       ("Kids Events in Houston in December", True), ("Best Delis, Po' Boys, and Sandwiches in Houston", False)]
for title, want in FAM:
    if bool(f.FAMILY_RE.search(title)) != want:
        bad += 1
        print("NG family", title)
_P = _dt.datetime(2026, 10, 21, 15, tzinfo=_dt.timezone.utc)   # 水曜
for title, want in [("Fun at Friday’s Trunk or Tree-t", "2026-10-23"), ("Book Sale is Nov. 6-8", "2026-11-06"),
                    ("Kids Events in Houston in December", None)]:
    if f.local_date(title, _P) != want:
        bad += 1
        print("NG local_date", title, f.local_date(title, _P))
# お出かけ先(2026-10-26):A&M のスポーツ・夜の店・会議は外す/種類の分類/HTML のイベント一覧
for title, cats, want in [("Gameday on Main Arkansas vs Texas A&M", [], True), ("Aggie Football Watch Party", [], True),
                          ("Midnight Yell", [], True), ("Open Mic Night At Murphy's Law", [], True),
                          ("Planning & Zoning Commission Meeting", [], True), ("Some Game", ["Aggie Sports"], True),
                          ("Pumpkin Patch at Lake Walk", [], False), ("Trunk or Treat So Kids Can Eat", [], False),
                          ("Brazos Valley Bombers Opening Night", [], False),
                          ("\"Remnants of 150 Years at Texas A&M University\" Exhibit", [], False)]:
    if f.outing_ng(title, cats) != want:
        bad += 1
        print("NG outing_ng", title)
for title, kind in [("Pumpkin Patch at Lake Walk", "公園・屋外"), ("Boo at the Zoo at Aggieland Safari", "動物"),
                    ("Holiday Lights Parade", "エンタメ"), ("Brazos Valley Bombers Baseball", "スポーツ"),
                    ("Kids Craft Day", "子供向け")]:
    if kind not in f.outing_kinds(title):
        bad += 1
        print("NG outing_kinds", title, f.outing_kinds(title))
_db = f.parse_dbryan(open(Path(__file__).parent / "fixtures" / "dbryan.html").read())
_bg = f.parse_bryangov(open(Path(__file__).parent / "fixtures" / "bryangov.html").read())
if len(_db) < 10 or not all(x["start"] for x in _db) or len(_bg) < 10 or not all(x["start"] for x in _bg):
    bad += 1
    print("NG html parsers", len(_db), len(_bg))
# 取り込んだ催し(calendar)は、情報源一覧にない名前でも地域・家族の印が消えない(10/26 の不具合)
import json as _json, subprocess as _sp, tempfile as _tf
_tmp = Path(_tf.mkdtemp()) / "d.json"
_tmp.write_text(_json.dumps({"items": [{"id": "t1", "title": "Pumpkin Patch at Lake Walk", "link": "https://example.com/e",
    "source": "Destination Bryan", "posted": "2026-10-26T00:00Z", "firstSeen": "2026-10-26T00:00Z", "expires": "2099-01-01",
    "region": "College Station", "calendar": True, "localDate": "2099-01-01", "stores": [], "cats": ["Outdoors"],
    "types": ["sale"], "pct": None, "price": None, "event": None, "eventNews": False}]}))
_sp.run([sys.executable, str(Path(__file__).parent.parent / "scripts" / "fetch_deals.py"), "--from-dir", str(_tmp.parent / "none"),
         "--out", str(_tmp), "--no-translate"], check=True, capture_output=True)
_x = _json.loads(_tmp.read_text())["items"][0]
if _x.get("region") != "College Station" or not _x.get("family"):
    bad += 1
    print("NG calendar region kept", _x.get("region"), _x.get("family"))
# 病院・訴訟のニュースはお出かけ先にしない(10/27)
if not f.outing_ng("Nation's first detransition clinic now open as result of Texas AG's settlement with Texas Children's Hospital"):
    bad += 1
    print("NG outing_ng hospital news")
# 朝のメール:ヒューストンはカレッジステーションの後ろの「ヒューストン」欄だけに出る(10/27 本人指定)
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import daily_digest as _dd, datetime as _dt
_t = _dt.datetime.now(_dd.CT).date().isoformat()
_base = {"posted": "2026-10-26T00:00Z", "firstSeen": "2099-01-01T00:00Z", "stores": [], "cats": [], "types": [], "link": "https://example.com/"}
_items = [{**_base, "id": "c", "title": "Kids Pumpkin Patch", "region": "College Station", "family": True, "date": _t, "sum": {"what": "CS家族"}},
          {**_base, "id": "h", "title": "Kids Pumpkin Patch", "region": "Houston", "family": True, "date": _t, "sum": {"what": "HOU家族"}},
          {**_base, "id": "hf", "title": "Free Donut", "region": "Houston", "freebie": {"kind": "store"}, "date": _t, "sum": {"what": "HOU無料"}},
          {**_base, "id": "f", "title": "Free Donut", "freebie": {"kind": "store"}, "date": _t, "sum": {"what": "全国無料"}}]
_title, _body, _ = _dd.build(_items, "2000-01-01T00:00Z", "")
_hou = _body.index("## 🏙 HS")
if not (_body.index("CS家族") < _hou < _body.index("HOU家族") and _body.index("全国無料") < _hou < _body.index("HOU無料")
        and _title.endswith("HS2")):
    bad += 1
    print("NG digest houston order", _title)
# キャラコラボ(10/27 本人指定:ポケモンとサンリオだけ):飲食・グッズのコラボは拾い、カード箱の値下げ・抽選・ほかのキャラは拾わない
for title, want in [("McDonald's Pokémon Happy Meal Returns Nov 4", ("food", "ポケモン")),
                    ("McDonald's Pokemon TCG Promotion to Launch in November for 30th Anniversary!", ("food", "ポケモン")),
                    ("Pokémon and McDonald's Reveal 15 New Happy Meal Toys Ahead of November Release", ("food", "ポケモン")),
                    ("Hello Kitty Fan? Grab a FREE Mystery Toy with Any Burger King Kids Meal!", ("food", "サンリオ")),
                    ("Stanley x Hello Kitty Quencher Tumbler Drops Today", ("goods", "サンリオ")),
                    ("Owala x Pokémon FreeSip Bottle", ("goods", "ポケモン")),
                    ("Score Domino’s x Minecraft Dungeons Exclusives", None),
                    ("McDonald’s Unveils New Disney Villains Boo Buckets", None),
                    ("Score 50¢ Sonic Corndogs on October 31st", None), ("Pokémon Elite Trainer Box $59.99", None),
                    ("Walmart Drawing TODAY at 5PM ET — Pokémon Cards Up For Grabs!", None)]:
    r = f.collab_info(title)
    if (r and (r["kind"], r["chars"][0])) != want:
        bad += 1
        print("NG collab", title, r)
# コラボ予定:見出しに日付がある飲食店のコラボは collabs.json に入り、手入力の予定と近ければ出典だけ足す
_cp = Path(_tf.mkdtemp()) / "c.json"
_cp.write_text(_json.dumps({"collabs": [{"id": "m", "store": "McDonald's", "chars": ["ポケモン"], "start": "2099-11-10", "end": "2099-12-14", "sources": []}]}))
_now = _dt.datetime(2099, 10, 27, tzinfo=_dt.timezone.utc)
_ci = [{"id": "a", "title": "McDonald's Pokémon Happy Meal Starts Nov 5", "link": "https://e.com/a", "source": "X", "posted": "2099-10-27T00:00Z",
        "stores": ["McDonald's"], "collab": {"chars": ["ポケモン"], "kind": "food"}},
       {"id": "b", "title": "Burger King Hello Kitty Meal Starts Nov 20", "link": "https://e.com/b", "source": "X", "posted": "2099-10-27T00:00Z",
        "stores": ["Burger King"], "collab": {"chars": ["サンリオ"], "kind": "food"}}]
f.update_collab_calendar(_ci, _now, _cp)
_cal = _json.loads(_cp.read_text())["collabs"]
if not (len(_cal) == 2 and _cal[0]["start"] == "2099-11-10" and _cal[0]["sources"][0]["url"] == "https://e.com/a"
        and _cal[1]["auto"] and _cal[1]["start"] == "2099-11-20"):
    bad += 1
    print("NG collab calendar", _cal)
_atom = f.parse_rss('<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Pokémon x Krispy Kreme Donuts</title>'
                    '<link rel="alternate" href="https://example.com/a"/><published>2026-10-27T10:00:00-05:00</published></entry></feed>')
if not (_atom and _atom[0]["link"] == "https://example.com/a" and f.parse_date(_atom[0]["date"])):
    bad += 1
    print("NG atom", _atom)
print(f"failures: {bad}")


# 期限の読み取りと、期限が読めない記事の残す日数(2026-10-27:古い無料情報が残る問題)
import datetime as _dt  # noqa: E402
_P = _dt.datetime(2026, 10, 20, 15, tzinfo=_dt.timezone.utc)
_EXP = [
    ("Fun, Free & Cheap Events | October 23 – October 25", "2026-10-25"),
    ("Free Can of Red Bull on October 26th – FIRST 5,000!", "2026-10-26"),
    ("Free Kids LEGO Workshop on 10/25", "2026-10-25"),
    ("FREE Keebler Cookies Through October 31st!", "2026-10-31"),
    ("Free PetSmart Halloween Events 2026", "2026-10-31"),
    ("Oct 30-Nov 2 Sale at Kohl's", "2026-11-02"),
    ("Black Friday Ad Leaks", None),
]
_bad = [(t, e, f.guess_expiry(t, _P)) for t, e in _EXP if f.guess_expiry(t, _P) != e]
assert f.guess_expiry("Pokemon Happy Meal arrives on Nov 10", _P, strict=True) is None, "コラボは開始日を期限にしない"
assert f.life_days({"title": "Hurry! FREE Pizza for the First 10,000!", "freebie": {"kind": "coupon"}}) == f.LIMITED_LIFE_DAYS
assert f.life_days({"title": "Free Cookie", "freebie": {"kind": "coupon"}}) == f.DEFAULT_LIFE_DAYS
assert f.life_days({"title": "Socks 50% off", "types": ["sale"]}) == f.SALE_LIFE_DAYS
print("expiry failures:", len(_bad), _bad if _bad else "")
assert not _bad
