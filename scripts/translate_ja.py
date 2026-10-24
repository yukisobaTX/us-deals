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
LAST_ERROR = {}
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")   # Google が常に最新の flash を指す別名。空なら一覧から自動で選ぶ
_MODEL = {}
PROMPT = (
    "以下は米国のお得情報ブログの記事見出しです(各行:id、掲載日、見出し)。"
    "それぞれを4項目に分けて、日本語で端的に書いてください。\n"
    "- store:店舗・ブランド名(英語のまま。不明なら \"\")\n"
    "- item:もらえるもの/安くなるもの(日本語、20字以内。金額は $ のまま)\n"
    "- when:日時(例「10/25(日)」「10/24 12〜16時」「〜10/31」「毎日正午ET」。掲載日を基準に Today 等を日付にする。不明なら \"\")\n"
    "- cond:条件(例「会員限定」「$10以上購入」「先着1万名」「要予約」「アプリ」。なければ \"\")\n"
    "- 誇張表現(Hurry!, WOW! など)は省く\n"
    "- 出力は JSON オブジェクトのみ: {\"id\": {\"store\":..., \"item\":..., \"when\":..., \"cond\":...}, ...}\n\n"
)


def _post_json(url, body, headers=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def pick_model(key):
    """使える flash 系の最新モデルを選ぶ(モデルの廃止に自動で追従する)。"""
    if GEMINI_MODEL:
        return GEMINI_MODEL
    if "m" in _MODEL:
        return _MODEL["m"]
    req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                                 headers={"x-goog-api-key": key, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        models = json.loads(r.read()).get("models", [])
    cands = []
    for m in models:
        name = m.get("name", "").split("/")[-1]
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        if not re.fullmatch(r"gemini-(\d+(?:\.\d+)?)-flash", name):   # lite・preview・日付付きは除く
            continue
        cands.append((float(re.search(r"\d+(?:\.\d+)?", name).group()), name))
    if not cands:
        raise RuntimeError("使える Gemini flash モデルが見つかりません")
    _MODEL["m"] = max(cands)[1]
    print(f"Gemini モデル: {_MODEL['m']}")
    return _MODEL["m"]


def gemini(items):
    """items: [(id, 掲載日, title)] → {id: {store, item, when, cond}}"""
    key = os.environ.get("GEMINI_API_KEY")
    if not key or not items:
        return {}
    lines = "\n".join(f"{i}\t{d}\t{t}" for i, d, t in items)
    res = _post_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{pick_model(key)}:generateContent",
        {"contents": [{"parts": [{"text": PROMPT + lines}]}],
         "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}},
        {"x-goog-api-key": key})
    text = res["candidates"][0]["content"]["parts"][0]["text"]
    out = json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip()))
    ids = {i for i, _, _ in items}
    res = {}
    for k, v in out.items():
        if k in ids and isinstance(v, dict) and str(v.get("item", "")).strip():
            res[k] = {f: str(v.get(f, "") or "").strip() for f in ("store", "item", "when", "cond")}
    return res


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
    """items: [(id, 掲載日, title)] → ({id: dict(Gemini) または str(MyMemory)}, 使った方法)。"""
    items = items[:limit]
    if not items:
        return {}, None
    if os.environ.get("GEMINI_API_KEY"):
        # 10件ずつ依頼。失敗した組はとばし、成功した分は使う(残りは次の回に)
        out = {}
        for k in range(0, min(len(items), 40), 10):
            try:
                out.update(gemini(items[k:k + 10]))
            except Exception as e:  # noqa: BLE001
                body = ""
                if hasattr(e, "read"):
                    try:
                        body = e.read().decode("utf-8", "replace")[:400]
                    except Exception:  # noqa: BLE001
                        pass
                LAST_ERROR["gemini"] = f"{e} {body}".strip()
                print(f"gemini 失敗: {LAST_ERROR['gemini']}")
                if "429" in str(e) or "40" in str(e)[:15]:
                    break
        if out:
            return out, "gemini"
        print("gemini で1件も要約できず → MyMemory に切り替え")
    out = {}
    for i, _, t in items:
        try:
            ja = mymemory(t)
        except Exception as e:  # noqa: BLE001
            print(f"mymemory 失敗: {e}")
            break
        if ja:
            out[i] = ja
        time.sleep(1)
    return out, "mymemory"


def mymemory_many(items, limit=20):
    """items: [(id, 掲載日, title)] → {id: 訳}。上限に当たったら止める。"""
    out = {}
    for i, _, t in items[:limit]:
        try:
            ja = mymemory(t)
        except Exception as e:  # noqa: BLE001
            LAST_ERROR["mymemory"] = str(e)
            break
        if not ja:
            break   # 1日の上限超過などは英語のエラー文が返る → 今回はここまで
        out[i] = ja
        time.sleep(1)
    return out


def gemini_once(items):
    """Gemini に1回だけ依頼(無料枠は1日の回数が少ないので、まとめて1回)。失敗は例外にせず {}。"""
    try:
        return gemini(items)
    except Exception as e:  # noqa: BLE001
        body = ""
        if hasattr(e, "read"):
            try:
                body = e.read().decode("utf-8", "replace")[:300]
            except Exception:  # noqa: BLE001
                pass
        LAST_ERROR["gemini"] = f"{e} {body}".strip()
        return {}
