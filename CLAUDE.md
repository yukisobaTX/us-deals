# お得ノート(us-deals)作業ルール

テキサス生活のお得情報(スーパー・雑貨/ホームセンター・レストラン/カフェ・ネット通販)を集めて一覧にし、毎朝1通メールで知らせる自分用サイト。

## 仕組み(すべて GitHub Actions・AI なし)
| ワークフロー | 時刻 | 役割 |
|---|---|---|
| Collect deals(scripts/fetch_deals.py) | 毎時 :17 | RSS を取得・分類し public/data/deals.json を更新。**通知はしない**(即時通知は 2026-10-26 に廃止) |
| Morning digest(scripts/daily_digest.py) | 毎朝 7:15 ごろ CT(夏冬とも) | **メールはこの1通だけ**。①今日・明日の無料情報(日付が今日・明日のもの+日付なしの新着。**完全無料=購入不要と飲食 BOGO だけ**、「$10以上購入で無料」「2つ買うと2つ無料」などは is_pure_free() で外す)を「店舗名:もらえるもの:日時:条件」+リンクで詳しく ②明後日〜14日先の無料情報と大型セールの新着は「日付 店舗:内容」の短文だけ(詳細はサイト)。載せるものがない日は送らない |
- 公開:Cloudflare Workers(静的アセット、public/)。main への push で自動反映。noindex・robots.txt で検索に出さない。

- 通知は Gmail から直接送る(scripts/mailer.py、us-market-note から流用。送信元名「お得ノート」、secret GMAIL_APP_PASSWORD・env GMAIL_USER。追加の宛先は workflow の env MAIL_TO にカンマ区切り。今は pinkpokepoke@gmail.com)。件名に [リポジトリ名]・(Issue #番号) が付かない。送れないときだけ @メンション付き Issue に切り替わる。
- 通知の Issue は閉じない(閉じると「Closed as completed」のメールが別に届くため)。

## 情報源のルール
- RSS は robots.txt で禁止されていないものだけ(Slickdeals は禁止なので使わない)。
- 保存するのは見出し・リンク・掲載日・分類・サムネイル画像の URL だけ。本文・画像ファイルは保存しない(サムネは配信元 RSS の thumbnail-image 等を直接表示)。
- 情報源:Hip2Save・Doctor of Credit・Fast Food Post(レストラン)・Money Saving Mom・The Freebie Guy・Moms Who Save・Houston on the Cheap(ヒューストンの催し)・カレッジステーション市のブログ(blog.cstx.gov。公園・図書館・催し)・Bryan+College Station 図書館(bcslibrary.org)・WTAW(カレッジステーションの地元ラジオ局。localOnly=催し・無料・お得の見出しだけ、事件・スポーツ・選挙は除外。robots.txt の Crawl-delay 600 秒 → 毎時1回なので可)。取得先は config/sources.json、店とキーワードは config/stores.json、公式リンク集は public/data/links.json。

## 地域(2026-10-26 追加)
- 本人はカレッジステーション在住。地元の情報を日々使えるように、items[].region に "College Station" / "Houston" を付ける。
- 付け方:region 付きの情報源(WTAW=College Station、Houston on the Cheap=Houston)はその地域。ほかの情報源も見出しの地名(fetch_deals.py の REGION_KW)で付ける。
- 朝のメール:「📍 地元(今日・明日と新着)」の欄。カレッジステーション周辺(最大10件)を先、ヒューストン(最大5件)を後。購入条件は問わない(催しも載せる)。この欄に入れたものは「今日・明日」から外す。
- サイト:「📍 地元」タブと、カードの 📍 地域ラベル。
- 👨‍👩‍👧 家族のお出かけ(2026-10-26 追加):地域の印がある記事のうち、家族・子供向けの語(FAMILY_RE:kids・family・story time・trunk or treat・pumpkin・zoo・museum・santa・parade・festival・book sale など)があれば items[].family=true。催しの日付 items[].localDate は local_date()(見出しの日付 → 曜日)。
  - 朝のメール:「👨‍👩‍👧 家族のお出かけ案(今日から1週間)」の欄。今日〜7日先(日付なしは新着だけ)、カレッジステーション(最大6件)→ヒューストン(最大4件)。この欄に入れたものは地元・今日明日の欄から外す。地元・家族の欄は「日付:見出し(日本語)」とリンクだけ(fmt_local)。
  - サイト:「👨‍👩‍👧 家族のお出かけ」タブ(過去の日付は出さない)と、カードの「家族向け M/D」ラベル。
  - 地元・家族の記事は Gemini で「何のイベントか(item)・場所(store)・日時(when)・費用/対象(cond)」に要約(translate_ja.EV_PROMPT、jaVia="gemini-ev")。見出しの直訳はしない。まとめ記事は「〜まとめ」と書く。材料は見出し+RSS の description 冒頭400字(DESC、この実行の間だけ。deals.json には保存しない)。1実行1回・1日5回まで(無料枠の合計は19回まで)。家族向け・日付の近いものから。Gemini が使えないときは機械翻訳の見出し+localDate。
  - メールの地元・家族の行:「日時:[何のイベントか](リンク)(場所・費用)」(fmt_local)。
- 調査済みで使わないもの:KBTX(AI 系ボットを robots.txt で拒否、全国ニュースが多い)、ABC13(AI 系ボット拒否)、Community Impact(RSS なし・/article/ 禁止)、Macaroni KID(RSS なし)、Texas A&M のカレンダー(学内向けが大半で1000件と多い)、Houston Moms(ドメイン売却済み)、Collaborative for Children(RSS が2023年で止まっている)。

## 変えるとき
- 店を足す:config/stores.json に追記 → `python3 tests/test_classify.py` で failures: 0。
- 分類を変えたら tests/test_classify.py に1件足す。
- 期限は見出しの「Today Only」「through 10/31」などから推定。読めないものは画面で「掲載日 + 7日」を目安にする。21日より古い記事は自動で消える。
- 「注目」= 無料、または 70%以上の値引き。
- 「無料でもらえる」(freebie)= fetch_deals.py の freebie_info()。送料無料・キャッシュバック後無料・懸賞・お試し・退役軍人向け・電子書籍・「〜で稼ぐ」などは除外。「Freebies」まとめ記事はクーポン扱い。別の情報源の同じ話題は mark_duplicates() で dup を付け、通知・画面から外す。店頭(イベント・日時・数量限定)とクーポンに分け、日付を見出しから読む。毎回すべての記事にかけ直す。画面の初期タブ(「無料・BOGO」)。
- BOGO(1つ買うと1つ無料、2-for-1)は**レストラン・カフェの飲食物だけ**「もらえる」扱い(freebie.bogo=true、通知あり・🥤BOGO 表示)。判定は is_food():stores.json の food の店名があれば対象、スーパー・雑貨の店名だけなら対象外、店名なしは飲み物・食べ物の語で判定。「BOGO 50% Off」は無料ではないので対象外。「on the house / complimentary」も飲食なら無料扱い。
- 日本語化:無料情報・大型セールの記事は Gemini(朝のメールの「今日・明日」に載るものを先に。gemini-flash-latest、無料枠は1日20回 → 1実行1回・1日15回まで、public/data/gemini-usage.json で数える)で4項目要約。セール記事と Gemini 不可時は MyMemory(1回25件まで)。
- 大型セール:config/stores.json の events(ブラックフライデー・プライムデー・免税週末など)。サイトの「🛍 大型セール」タブと、朝のメールの短文(前回以降の新着、セールごと最大3件)。即時通知はしない。予定は public/data/events.json(手で編集)。
- 並び順の既定は「日付順」(items[].date = 配布日 → 要約の日時 → 期限、日付なしは後ろ)。通知メールも1本のリストで日付順(🏬店頭・🎟クーポン)。
- 画面の JS は public/js/app.js。外部の見出しは textContent で入れる(innerHTML は使わない)。
- 試験:`python3 scripts/fetch_deals.py --from-dir tests/fixtures --out /tmp/x.json`(ネット不要)、`python3 scripts/daily_digest.py --force --dry-run`。

## 使えない情報源(調査済み 10/24)
- Instagram:API なし・規約で自動収集不可。Google News RSS・Chew Boom(2024年に終了)・Krazy Coupon Lady(RSS なし)も不可。Brand Eating は新メニュー中心で価値が低い。
