#!/usr/bin/env python3
"""Gemini の接続試験(手動実行用)。結果を public/data/gemini-debug.json に保存。キーは書き出さない。"""
import json, os, time, urllib.request
from pathlib import Path
KEY = os.environ["GEMINI_API_KEY"]
B = "https://generativelanguage.googleapis.com/v1beta/models"
out = {"models": [], "tests": []}
try:
    req = urllib.request.Request(B + "?pageSize=200", headers={"x-goog-api-key": KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        ms = json.loads(r.read()).get("models", [])
    out["models"] = [m["name"].split("/")[-1] for m in ms if "generateContent" in m.get("supportedGenerationMethods", [])]
except Exception as e:
    out["modelsError"] = str(e)
cands = [m for m in out["models"] if "flash" in m][:6]
for model in cands:
    for gc in ({}, {"thinkingConfig": {"thinkingBudget": 0}}, {"thinkingConfig": {"thinkingLevel": "minimal"}}):
        t = time.time()
        rec = {"model": model, "config": gc}
        try:
            body = {"contents": [{"parts": [{"text": "Translate to Japanese in 10 words: FREE Pet Photos with Santa at Petco on December 12th"}]}],
                    "generationConfig": {"temperature": 0.2, **gc}}
            req = urllib.request.Request(f"{B}/{model}:generateContent", data=json.dumps(body).encode(), method="POST",
                                         headers={"x-goog-api-key": KEY, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read())
            rec["text"] = d["candidates"][0]["content"]["parts"][0]["text"][:100]
        except Exception as e:
            b = ""
            if hasattr(e, "read"):
                try: b = e.read().decode()[:300]
                except Exception: pass
            rec["error"] = f"{e} {b}"
        rec["sec"] = round(time.time() - t, 1)
        out["tests"].append(rec)
        if "text" in rec and gc == {}:
            break
Path("public/data/gemini-debug.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
