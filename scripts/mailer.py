"""通知メールを Gmail(SMTP)から直接送る(us-market-note の mailer.py を流用)。
GitHub の通知メールは件名に [リポジトリ名] と (Issue #番号) が付くため、2026-10-24 に持ち主の依頼で切り替えた。

環境変数(GitHub Actions の secrets / env):
- GMAIL_APP_PASSWORD … Gmail のアプリ パスワード(16文字。スペースは無視する)。リポジトリの secret
- GMAIL_USER … 送信元のアドレス(workflow の env に書く)。MAIL_TO を省くと宛先も同じ
使い方:send_mail(件名, Markdown の本文) → 送れたら True。設定がない・失敗したら False(呼び出し側が GitHub の通知に切り替える)。
送ったあと、同じアプリ パスワードで IMAP にログインし、そのメールに Gmail の「重要」の印を付けて未読・受信トレイに戻す
(10/24 持ち主の依頼。自分宛てのメールは既読・重要なしで届くため)。印付けに失敗してもメールは届いているので、送信は成功とする。
"""
from __future__ import annotations

import html
import imaplib
import os
import re
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

FROM_NAME = "お得ノート"
LAST_MARK = ""   # 直前の「重要」の印付けの結果(Issue の記録に残す)


LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


def _plain(md: str) -> str:
    s = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    s = LINK_RE.sub(r"\1 \2", s)
    s = re.sub(r"<br><sub>(.*?)</sub>", r"\n    (\1)", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"^#{1,6}\s*", "■ ", s, flags=re.M)
    return s.strip() + "\n"


def _html(md: str) -> str:
    s = re.sub(r"<!--.*?-->", "", md, flags=re.S).strip()
    out, in_list = [], False
    for line in s.splitlines():
        t = html.escape(line)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        links = []
        def _ln(m):
            links.append(f'<a href="{m.group(2)}" style="color:#b5521b">{m.group(1)}</a>')
            return f"\x00{len(links) - 1}\x00"
        t = LINK_RE.sub(_ln, t)
        t = re.sub(r"(https?://[^\s<)()]+)", r'<a href="\1">\1</a>', t)
        t = re.sub(r"\x00(\d+)\x00", lambda m: links[int(m.group(1))], t)
        t = re.sub(r"&lt;br&gt;&lt;sub&gt;(.*?)&lt;/sub&gt;",
                   r'<br><span style="font-size:12px;color:#888">\1</span>', t)
        if t.startswith("- "):
            if not in_list:
                out.append('<ul style="margin:4px 0 8px;padding-left:20px">')
                in_list = True
            out.append(f"<li>{t[2:]}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        m = re.match(r"#{1,6}\s*(.*)", t)
        if m:
            out.append(f'<h3 style="font-size:15px;margin:14px 0 4px">{m.group(1)}</h3>')
        elif t.strip():
            out.append(f'<p style="margin:4px 0">{t}</p>')
    if in_list:
        out.append("</ul>")
    return ('<div style="font-family:-apple-system,Segoe UI,Hiragino Sans,Meiryo,sans-serif;font-size:14px;line-height:1.6">'
            + "\n".join(out) + "</div>")


def configured() -> bool:
    return bool(os.environ.get("GMAIL_APP_PASSWORD") and os.environ.get("GMAIL_USER"))


def send_mail(subject: str, body_md: str) -> bool:
    if not configured():
        print("メール:GMAIL_APP_PASSWORD / GMAIL_USER がないので送らない(GitHub の通知に切り替え)")
        return False
    user = os.environ["GMAIL_USER"].strip()
    # 宛先:自分+ MAIL_TO(カンマ区切りで複数可)。重複は除く
    to_list = [user] + [a.strip() for a in os.environ.get("MAIL_TO", "").split(",") if a.strip()]
    to = ", ".join(dict.fromkeys(a.lower() for a in to_list))
    pw = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "").strip()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((FROM_NAME, user))
    msg["To"] = to
    msg["Message-ID"] = mid = make_msgid(domain="us-deals")
    msg["Importance"] = "high"   # Outlook など向け(Gmail の「重要」は下の IMAP で付ける)
    msg["X-Priority"] = "1"
    msg.set_content(_plain(body_md))
    msg.add_alternative(_html(body_md), subtype="html")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30) as s:
            s.login(user, pw)
            s.send_message(msg)
        print("メール送信:", subject)
    except Exception as e:  # noqa: BLE001
        print(f"メール送信に失敗(GitHub の通知に切り替え): {type(e).__name__} {str(e)[:160]}")
        return False
    global LAST_MARK
    try:
        LAST_MARK = mark_important(user, pw, mid)
    except Exception as e:  # noqa: BLE001
        LAST_MARK = f"失敗 {type(e).__name__} {str(e)[:120]}"
    print("「重要」の印付け:", LAST_MARK)
    return True


def _all_mail(conn: imaplib.IMAP4_SSL) -> str:
    """「すべてのメール」のフォルダ名(表示言語で名前が変わるので \\All の印で探す)。"""
    _, rows = conn.list()
    for r in rows or []:
        line = r.decode(errors="replace")
        if "\\All" in line:
            m = re.search(r'"([^"]+)"\s*$', line) or re.search(r"(\S+)\s*$", line)
            if m:
                return m.group(1)
    return "[Gmail]/All Mail"


def mark_important(user: str, pw: str, message_id: str, tries: int = 6) -> str:
    """送ったメールを Message-ID で探し、重要・受信トレイ・未読にする(届くまで数秒かかるので待ちながら探す)。"""
    conn = imaplib.IMAP4_SSL("imap.gmail.com", 993, ssl_context=ssl.create_default_context())
    try:
        conn.login(user, pw)
        folder = _all_mail(conn)
        conn.select('"' + folder.replace('"', '') + '"')
        uids = []
        for i in range(tries):
            _, data = conn.uid("SEARCH", None, "X-GM-RAW", f'"rfc822msgid:{message_id.strip("<>")}"')
            uids = (data[0] or b"").split()
            if uids:
                break
            time.sleep(3 + 2 * i)
        if not uids:
            return "送ったメールが見つからない(時間切れ)"
        for u in uids:
            conn.uid("STORE", u, "+X-GM-LABELS", "(\\Important \\Inbox)")
            conn.uid("STORE", u, "-FLAGS", "(\\Seen)")
        return "OK"
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass
