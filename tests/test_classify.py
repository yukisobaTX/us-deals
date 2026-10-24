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
    ("Weee! $20 Off First Order", [], lambda r: r["stores"] == ["Weee!"]),
]

bad = 0
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
