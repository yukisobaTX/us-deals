#!/usr/bin/env python3
"""見出しを日本語にする(標準ライブラリのみ)。

- GEMINI_API_KEY があれば Gemini で「何が・どこで・いつ・条件」を短く要約(まとめて1回で依頼)。
- なければ MyMemory(無料・登録不要、1日約5,000字まで)で機械翻訳。
- どちらも失敗したら None(画面・メールは英語の見出しのまま)。
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

UA = "us-deals-personal/1.0"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
PROMPT = (
    "以下は米国のお得情報ブログの記事見出しです。それぞれを日本語で簡潔に要約してください。\n"
    "- 40字程度まで。何がもらえる/安くなるか・どこで・いつ・条件(会員限定・購入条件・先着など)を優先\n"
    "- 店名・ブランド名は英語のまま。金額は $ のまま。誇張表現(Hurry!, WOW! など)は省く\n"
    "- 出力は JSON オブジェクトのみ: {\"id\": \"要約\", ...}\n\n"
)


def _post_json(url, body, headers=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def gemini(items):
    """items: [(id, title)] → {id: ja}"""
    key = os.environ.get("GEMINI_API_KEY")
    if not key or not items:
        return {}
    lines = "\n".join(f"{i}\t{t}" for i, t in items)
    res = _post_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        {"contents": [{"parts": [{"text": PROMPT + lines}]}],
         "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}},
        {"x-goog-api-key": key})
    text = res["candidates"][0]["content"]["parts"][0]["text"]
    out = json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip()))
    ids = {i for i, _ in items}
    return {k: str(v).strip() for k, v in out.items() if k in ids and str(v).strip()}


def mymemory(title):
    q = urllib.parse.urlencode({"q": title[:450], "langpair": "en|ja"})
    req = urllib.request.Request(f"https://api.mymemory.translated.net/get?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
    t = (d.get("responseData") or {}).get("translatedText") or ""
    # 上限超過などはエラー文が英語で返るので捨てる
    if d.get("responseStatus") != 200 or not re.search(r"[぀-ヿ一-鿿]", t):
        return None
    return t.strip()


def translate(items, limit=40):
    """items: [(id, title)] → ({id: ja}, 使った方法)。limit 件まで。"""
    items = items[:limit]
    if not items:
        return {}, None
    if os.environ.get("GEMINI_API_KEY"):
        try:
            out = {}
            for k in range(0, len(items), 20):
                out.update(gemini(items[k:k + 20]))
            if out:
                return out, "gemini"
        except Exception as e:  # noqa: BLE001
            print(f"gemini 失敗 → MyMemory に切り替え: {e}")
    out = {}
    for i, t in items:
        try:
            ja = mymemory(t)
        except Exception as e:  # noqa: BLE001
            print(f"mymemory 失敗: {e}")
            break
        if ja:
            out[i] = ja
        time.sleep(1)
    return out, "mymemory"
