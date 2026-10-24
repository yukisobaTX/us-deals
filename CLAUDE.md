# お得ノート(us-deals)作業ルール

テキサス生活のお得情報(スーパー・雑貨/ホームセンター・レストラン/カフェ・ネット通販)を集めて一覧にし、毎朝1通メールで知らせる自分用サイト。

## 仕組み(すべて GitHub Actions・AI なし)
| ワークフロー | 時刻 | 役割 |
|---|---|---|
| Collect deals(scripts/fetch_deals.py → freebie_alert.py) | 毎時 :17 | RSS を取得・分類し public/data/deals.json を更新。無料でもらえる新着があれば即 Issue(ラベル freebie-alert、@yukisobaTX)で通知 |
| Morning digest(scripts/daily_digest.py) | 毎朝 7:15 ごろ CT(夏冬とも) | 即時通知済みの新着は除き、今日・明日の店頭配布のリマインド。**無料でもらえるものだけ**を Issue(ラベル deals-digest、@yukisobaTX)で通知。店頭配布(日付順・今日/明日の分は再掲)と無料クーポン。該当なしの日は送らない |
- 公開:Cloudflare Workers(静的アセット、public/)。main への push で自動反映。noindex・robots.txt で検索に出さない。

- 通知は Gmail から直接送る(scripts/mailer.py、us-market-note から流用。送信元名「お得ノート」、secret GMAIL_APP_PASSWORD・env GMAIL_USER。追加の宛先は secret MAIL_TO にカンマ区切り)。件名に [リポジトリ名]・(Issue #番号) が付かない。送れないときだけ @メンション付き Issue に切り替わる。
- 通知の Issue は閉じない(閉じると「Closed as completed」のメールが別に届くため)。

## 情報源のルール
- RSS は robots.txt で禁止されていないものだけ(Slickdeals は禁止なので使わない)。
- 保存するのは見出し・リンク・掲載日・分類・サムネイル画像の URL だけ。本文・画像ファイルは保存しない(サムネは配信元 RSS の thumbnail-image 等を直接表示)。
- 取得先は config/sources.json、店とキーワードは config/stores.json、公式リンク集は public/data/links.json。

## 変えるとき
- 店を足す:config/stores.json に追記 → `python3 tests/test_classify.py` で failures: 0。
- 分類を変えたら tests/test_classify.py に1件足す。
- 期限は見出しの「Today Only」「through 10/31」などから推定。読めないものは画面で「掲載日 + 7日」を目安にする。21日より古い記事は自動で消える。
- 「注目」= 無料、または 70%以上の値引き。
- 「無料でもらえる」(freebie)= fetch_deals.py の freebie_info()。送料無料・BOGO・キャッシュバック後無料・懸賞・お試し・退役軍人向けなどは除外。店頭(イベント・日時・数量限定)とクーポンに分け、日付を見出しから読む。毎回すべての記事にかけ直す。画面の初期タブ。
- 日本語化:無料情報は Gemini(gemini-flash-latest、無料枠は1日20回 → 1実行1回・1日15回まで、public/data/gemini-usage.json で数える)で4項目要約。セール記事と Gemini 不可時は MyMemory(1回25件まで)。
- 大型セール:config/stores.json の events(ブラックフライデー・プライムデー・免税週末など)。日程発表・開始・チラシ公開の記事(EVENT_NEWS_RE)は即時通知(最大8件、状態は alert-state.json の lastEvent)、ほかはサイトの「🛍 大型セール」タブと朝のまとめ(セールごと最大5件)。予定は public/data/events.json(手で編集)。
- 並び順の既定は「日付順」(items[].date = 配布日 → 要約の日時 → 期限、日付なしは後ろ)。通知メールも1本のリストで日付順(🏬店頭・🎟クーポン)。
- 画面の JS は public/js/app.js。外部の見出しは textContent で入れる(innerHTML は使わない)。
- 試験:`python3 scripts/fetch_deals.py --from-dir tests/fixtures --out /tmp/x.json`(ネット不要)、`python3 scripts/daily_digest.py --force --dry-run`。
