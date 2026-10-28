"""ポータル(my-portal)経由で iPhone にプッシュ通知を送る小さな部品。AI なし。

認証は GitHub Actions の OIDC トークン(workflow に permissions: id-token: write が必要)。
secret は不要で、ポータル側は送り元のリポジトリ名を確かめてから全端末に配る。
送れなくても例外は出さず False を返す(メールなど本来の処理は止めない)。
us-market-note の push_portal() と同じ作り。お得ノート・Bio CDMO Daily・クレカで共用(同じ内容をコピー)。
"""
import json
import os
import urllib.request

PORTAL = os.environ.get("PORTAL_URL", "https://my-portal.10baki-c03.workers.dev")


def push(title: str, body: str, url: str = "", tag: str = "") -> bool:
    """1台以上に届いたら True。url を空にするとポータル側の既定(そのサイトのカード)を開く。"""
    req_url, tok = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL"), os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not req_url or not tok:
        print("プッシュ:OIDC が使えない(id-token: write がない or ローカル実行)ので送らない")
        return False
    try:
        r = urllib.request.Request(req_url + "&audience=my-portal", headers={"Authorization": f"bearer {tok}"})
        with urllib.request.urlopen(r, timeout=15) as res:
            jwt = json.loads(res.read())["value"]
        data = json.dumps({"title": title[:80], "body": body[:300], "url": url, "tag": tag}, ensure_ascii=False).encode()
        r = urllib.request.Request(PORTAL + "/api/push/notify", data=data, method="POST",
                                   headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json",
                                            "User-Agent": "portal-push-actions"})
        with urllib.request.urlopen(r, timeout=20) as res:
            out = json.loads(res.read())
        print(f"プッシュ:{out.get('sent')}/{out.get('total')} 台に送信")
        return bool(out.get("sent"))
    except Exception as e:  # noqa: BLE001
        print("プッシュ:送れなかった", type(e).__name__, str(e)[:200])
        return False
