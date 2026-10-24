# お得ノート(us-deals)作業ルール

テキサス生活のお得情報(スーパー・雑貨/ホームセンター・レストラン/カフェ・ネット通販)を集めて一覧にし、毎朝1通メールで知らせる自分用サイト。

## 仕組み(すべて GitHub Actions・AI なし)
| ワークフロー | 時刻 | 役割 |
|---|---|---|
| Collect deals(scripts/fetch_deals.py) | 3時間ごと(:17 UTC) | RSS を取得・分類し public/data/deals.json を更新 |
| Morning digest(scripts/daily_digest.py) | 毎朝 7:41 CT(夏冬とも) | **無料でもらえるものだけ**を Issue(ラベル deals-digest、@yukisobaTX)で通知。店頭配布(日付順・今日/明日の分は再掲)と無料クーポン。該当なしの日は送らない。前の Issue は閉じる |
- 公開:Cloudflare Workers(静的アセット、public/)。main への push で自動反映。noindex・robots.txt で検索に出さない。

## 情報源のルール
- RSS は robots.txt で禁止されていないものだけ(Slickdeals は禁止なので使わない)。
- 保存するのは見出し・リンク・掲載日・分類だけ。本文・画像は保存も表示もしない。
- 取得先は config/sources.json、店とキーワードは config/stores.json、公式リンク集は public/data/links.json。

## 変えるとき
- 店を足す:config/stores.json に追記 → `python3 tests/test_classify.py` で failures: 0。
- 分類を変えたら tests/test_classify.py に1件足す。
- 期限は見出しの「Today Only」「through 10/31」などから推定。読めないものは画面で「掲載日 + 7日」を目安にする。21日より古い記事は自動で消える。
- 「注目」= 無料、または 70%以上の値引き。
- 「無料でもらえる」(freebie)= fetch_deals.py の freebie_info()。送料無料・BOGO・キャッシュバック後無料・懸賞・お試し・退役軍人向けなどは除外。店頭(イベント・日時・数量限定)とクーポンに分け、日付を見出しから読む。毎回すべての記事にかけ直す。画面の初期タブ。
- 画面の JS は public/js/app.js。外部の見出しは textContent で入れる(innerHTML は使わない)。
- 試験:`python3 scripts/fetch_deals.py --from-dir tests/fixtures --out /tmp/x.json`(ネット不要)、`python3 scripts/daily_digest.py --force --dry-run`。
