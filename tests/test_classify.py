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
    ("Subway BOGO FREE Footlongs Coming October 27th", None, None),
    ("NEW Walmart Promo Codes: $10 Off + Free Express Delivery", None, None),
]
bad = 0
for title, kind, when in FREEBIES:
    r = f.freebie_info(title, P)
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
print(f"failures: {bad}")
sys.exit(1 if bad else 0)
