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
- 情報源(RSS):Hip2Save・Doctor of Credit・Fast Food Post(レストラン)・Money Saving Mom・The Freebie Guy・Moms Who Save・Houston on the Cheap(ヒューストンの催し)・カレッジステーション市のブログ(blog.cstx.gov。公園・図書館・催し)・Bryan+College Station 図書館(bcslibrary.org)・Sporked/The Impulsive Buy/My Nintendo News(collabOnly=キャラコラボの見出しだけ。下記)・WTAW(カレッジステーションの地元ラジオ局。localOnly=催し・無料・お得の見出しだけ、事件・スポーツ・選挙は除外。robots.txt の Crawl-delay 600 秒 → 毎時1回なので可)。取得先は config/sources.json、店とキーワードは config/stores.json、公式リンク集は public/data/links.json。

## 地域(2026-10-26 追加)
- 本人はカレッジステーション在住。地元の情報を日々使えるように、items[].region に "College Station" / "Houston" を付ける。
- 付け方:region 付きの情報源(WTAW=College Station、Houston on the Cheap=Houston)はその地域。ほかの情報源も見出しの地名(fetch_deals.py の REGION_KW)で付ける。
- 朝のメール:「📍 地元(今日・明日と新着)」の欄。カレッジステーション周辺(最大10件)。ヒューストン(最大5件)は最後の「🏙 ヒューストン」欄(10/27〜)。購入条件は問わない(催しも載せる)。この欄に入れたものは「今日・明日」から外す。
- サイト:「📍 地元」タブと、カードの 📍 地域ラベル。
- 👨‍👩‍👧 家族のお出かけ(2026-10-26 追加):地域の印がある記事のうち、家族・子供向けの語(FAMILY_RE:kids・family・story time・trunk or treat・pumpkin・zoo・museum・santa・parade・festival・book sale など)があれば items[].family=true。催しの日付 items[].localDate は local_date()(見出しの日付 → 曜日)。
  - 朝のメール:「👨‍👩‍👧 家族のお出かけ案(今日から1週間)」の欄。今日〜7日先(日付なしは新着だけ)、カレッジステーション(最大6件)→ヒューストン(最大4件)。この欄に入れたものは地元・今日明日の欄から外す。地元・家族の欄は「日付:見出し(日本語)」とリンクだけ(fmt_local)。
  - サイト:「👨‍👩‍👧 家族のお出かけ」タブ(過去の日付は出さない)と、カードの「家族向け M/D」ラベル。
  - 地元・家族の記事は Gemini で「何のイベントか(item)・場所(store)・日時(when)・費用/対象(cond)」に要約(translate_ja.EV_PROMPT、jaVia="gemini-ev")。見出しの直訳はしない。まとめ記事は「〜まとめ」と書く。材料は見出し+RSS の description 冒頭400字(DESC、この実行の間だけ。deals.json には保存しない)。1実行1回・1日5回まで(無料枠の合計は19回まで)。家族向け・日付の近いものから。Gemini が使えないときは機械翻訳の見出し+localDate。
  - メールの行はすべて「日付：何が(10文字以内)；どこで」(daily_digest.line、本人指定 10/26)。何が=sum.what、どこで=sum.where(Gemini の2項目。なければ item・store を切り詰め)。日付は 今日/明日/M/D(曜)/随時。何がにリンク。
  - 件名は「お得ノート M/D:今日・明日N/家族N/地元N/今後N」の順(本人指定)。
  - メールの無料欄(今日・明日・今後)は**食べ物・もらえる物だけ**(本人指定 10/26)。公園・博物館の入場無料、教室・ワークショップ・読み聞かせ・イベント参加などの体験系(EXPERIENCE_RE)と、割引(DISCOUNT_RE:「50% off」など)は is_goods() で外す。サイトには残る。家族・地元の欄は対象外(催しを載せる欄なので)。
- 調査済みで使わないもの:KBTX(AI 系ボットを robots.txt で拒否、全国ニュースが多い)、ABC13(AI 系ボット拒否)、Community Impact(RSS なし・/article/ 禁止)、Macaroni KID(RSS なし)、Texas A&M のカレンダー(学内向けが大半で1000件と多い)、Houston Moms(ドメイン売却済み)、Collaborative for Children(RSS が2023年で止まっている)。

## お出かけ先(カレッジステーション周辺、2026-10-26 追加・本人指定)
- 本人の希望:遊び場・お出かけ先になる公園イベント・動物(動物園・サファリ)・エンタメ・スポーツを充実させる。**A&M 関連のスポーツは不要**。
- 情報源(イベント一覧):GitHub Actions からは取れない(ブライアン市は 403、Destination Bryan は一覧が空)ため、**Claude の朝の定期実行が Firecrawl で読み、scripts/import_events.py で取り込む**。
  - Destination Bryan(観光局)https://www.destinationbryan.com/events/ と ?page=2・?page=3(robots.txt は /cpresources/・/vendor/ 以外許可)。
  - ブライアン市の催し https://events.bryantx.gov/default/List(今月分。? 付きは robots.txt で不可、Crawl-delay 15)。
  - import_events.py:入力は [{title, link, start, end, category, source, what, where, item, when, cond}]。outing_ng() で除外、既存は開催日・要約を更新、新規は region=College Station・calendar=true・jaVia=claude-ev。
  - fetch_deals.py の parse_dbryan()・parse_bryangov()・html/everyHours/delay の仕組みは、Actions で取れるようになったとき用に残している(tests/fixtures の HTML で試験)。
  - 見送り:Visit College Station(visit.cstx.gov/events。一覧が画面上で読み込まれず取れない)、Tockify の図書館カレンダー(/api/ が robots.txt で不可)、The Eagle(RSS が全国の芸能記事)、Aggieland Safari・Children's Museum(催しは Facebook・Instagram のみ)→ サイトの「家族のお出かけ」タブの公式リンク集(links.json の cat=family)に載せる。
- 除外 outing_ng():A&M のスポーツ(AGGIE_SPORTS_RE:Aggie/A&M+試合・vs・Gameday・Midnight Yell・Kyle Field など、カテゴリ Aggie Sports)、夜の店の定例(ADULT_NIGHT_RE:bar・pub・open mic・karaoke・trivia・mixology など、カテゴリ Nightlife)、会議(MEETING_RE)。A&M の博物館・展示は残す。
- 種類 outing_kinds() → items[].outing:公園・屋外🌳/動物🦒/エンタメ🎪/スポーツ⚽/子供向け🧒。outing がある地元記事は family=true(家族のお出かけ欄・タブに入る)。
- イベント一覧の記事は calendar=true、localDate=次の開催日(毎回更新)、expires=終了日 or 開催日。2週間以上続くもの(long_running)はメールで「〜M/D」と表示し、家族欄の後ろに回す。
- メールの家族欄:カレッジステーション最大10件・ヒューストン最大4件。行の先頭に種類の絵文字。

## カレッジステーション優先・ヒューストンは分ける(2026-10-27 本人指定)
- **カレッジステーション(在住地)と全国の情報を先に、ヒューストンは必ず後半に分けて書く。**
- 朝のメール(daily_digest.build):🎁今日・明日 → 👨‍👩‍👧家族(カレッジステーション周辺のみ)→ 📍地元(同)→ 📅今後・🛍大型セール → 最後に「🏙 ヒューストン」欄(家族のお出かけ・催し・無料/BOGO 2週間分 最大5件)。region=Houston の無料情報は今日・明日・今後から外してヒューストン欄へ。件名は「今日・明日N/家族N/地元N/今後N/ヒューストンN」(家族・地元はカレッジステーションの件数)。
- サイト(app.js):「👨‍👩‍👧 家族のお出かけ」「📍 カレッジステーション」はカレッジステーションのみ。「🏙 ヒューストン」タブを別に置く(家族向けを先に)。ほかのタブ(無料・すべて等)はヒューストンの記事を末尾に回し、「🏙 ヒューストン」の区切りを入れる。リンク集は links.json の cat=houston をヒューストンタブだけに出す。
- お出かけの除外に NEWS_NG_RE(病院・訴訟・行政のニュース)を追加(「Children's Hospital」を子供向けと誤判定したため)。
- **表記は略記:カレッジステーション=CS、ヒューストン=HS**(本人指定 10/27)。メールは daily_digest.abbr()、サイトは app.js の abbr() で表示時に置き換える(保存データの region は "College Station"/"Houston" のまま)。要約の指示(translate_ja・朝の定期実行)も「HS各地」などの略記で。
- 試験:tests/test_classify.py に、メールでヒューストンがカレッジステーションより後ろの欄に出ることの確認を入れている。

## Claude による要約(2026-10-26 追加・本人選択)
- Gemini の無料枠(1日20回)が足りないため、毎朝 6:41 CT に Claude の定期実行(scheduled task「お得ノート 朝の要約」)が、朝のメールに載る記事と地元・家族の記事の要約(what・where など)を作る。
- 手順:`python3 scripts/claude_pending.py > /tmp/pending.json`(要約が必要な記事を書き出す。daily_digest.build() で選ばれる記事+日付が過ぎていない地元記事のうち、jaVia が claude/claude-ev でないか what がないもの)→ Claude が要約 JSON を作る → `python3 scripts/apply_summaries.py <json>`(what 10字・where 15字に切り詰め、空の項目は前の要約を残す、jaVia="claude"/"claude-ev")→ commit・push。
- **キャラコラボの記事(items[].collab)の要約**:what は何のコラボ商品か(キャラ名はメールの【】に別に出るので繰り返さない。例「限定タンブラー」「キッズミール玩具」「限定バケツ」「コラボ菓子」)、where は販売店・チェーン名(例「McDonald's」「Target」)、item は「〇〇×キャラの限定△△」、when は発売日・開始日、cond は「数量限定」「キッズミール購入」など。
- fetch_deals.py は jaVia が SUMMARIZED(gemini・gemini-ev・claude・claude-ev)の要約を上書きしない。Gemini は毎時の収集で補助として残す。

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

## ポータルへのプッシュ通知(2026-10-27 追加・本人指定)
- 朝のまとめ(7:15)で、**当日の**無料・BOGO(今日・明日欄のうち日付が今日のもの+日付なしの新着)があれば、`scripts/portal_push.py` でポータル(my-portal)経由で iPhone に通知する(最大4件「何が；どこで」)。該当なしの日は送らない。
- **メールは家族あて(pinkpokepoke)にも必要なので従来どおり送る**(本人指定)。テスト送信・dry-run ではプッシュしない。認証は OIDC(digest.yml に id-token: write)。

## 🧸 キャラコラボ(2026-10-27 本人指定:**ポケモンとサンリオだけ**)
- 本人の希望:ファストフードや各種商品(ボトル・タンブラーなど)と、**ポケモン・サンリオ**のコラボ情報を載せる。11月のマック×ポケモンのような予定を確実に把握する。ほかのキャラ(ディズニー等)は載せない(同日 本人指定で絞り込み)。
- 判定 fetch_deals.collab_info() → items[].collab = {"chars": [日本語名], "kind": "food"|"goods"}。毎回すべての記事にかけ直す。キャラの一覧は config/stores.json の collab.core(broad は空)。
  - キャラ名+(飲食の語・グッズの語・コラボの語)で拾う。
  - 除外:LEGO・抽選・懸賞(COLLAB_NG_RE)。カード商品(CARD_RE:ポケカの箱・booster など)は値下げ記事が多いので外すが、**飲食店の店名かハッピーセット/キッズミールがあれば拾う**(マックのポケカ付きハッピーセットのため)。
  - kind:飲食店の店名がある、または飲食の語だけ → food(🍔)、それ以外 → goods(🎁)。
- 店名・値引きの語がなくてもコラボなら載せる(classify が None のとき既定の分類を付ける)。
- 情報源:既存の RSS に加え、collabOnly(コラボの見出しだけ拾う)の Sporked(robots.txt で /feed/atom/ だけ許可 → Atom)・The Impulsive Buy・My Nintendo News(usOnly=米国の店名か US/America の語がある見出しだけ。日本だけのコラボが多いため)。試して外したもの:PokeBeach(Actions から HTTP 500)、Essential Japan(RSS が出ない)。parse_rss は Atom にも、parse_date は ISO 形式にも対応。
- **コラボ予定 public/data/collabs.json**(RSS の記事は21日で消えるので、予定は別に持つ):
  - 手入力の予定(store・chars・title・what・start・end・status=公式/報道(未公式)/開催中・note・sources)。**毎週日曜 18:23 CT に Claude の定期実行(scheduled task「お得ノート ポケモン・サンリオ コラボ週次チェック」trig_01Xy7SyDPKdZ43voDfBaew5o)が検索して更新**(本人指定 10/27)。チャットで頼まれたときも Claude が調べて入れる(ダブルチェック:2つ以上の報道、日付が食い違えば新しい方+note に旧日程)。
  - 自動:update_collab_calendar() が、飲食店のコラボ記事で見出しに開始日があれば auto: true で追加。手入力の予定と同じ店・キャラで開始日±21日なら、日付は変えず sources に出典だけ足す。終了日+3日(自動は開始日+14日)を過ぎたら消える。
  - 2026-10-27 時点:McDonald's ポケモン30周年ハッピーセット 11/10〜12/14(未公式。10/27 PokeBeach が店舗で確認。9月の報道は 11/5〜12/9)、Burger King ハローキティ&フレンズのキッズミール(10/22 開始確認、リークでは 11/30 まで)。
- 朝のメール:「🧸 ポケモン・サンリオ コラボ」欄(今後・大型セールの後、HS の前)。
  - 📅 予定・まもなく終了(collab_plan):2週間以内に始まる予定、今日始まる予定、3日以内に終わる予定。行は「11/10(火)〜12/14(月)：🍔【ポケモン】ハッピーセット；McDonald's(未公式)」。
  - 🆕 新着:前回のまとめ以降の新着で、ほかの欄・予定に出ていないもの最大6件(飲食を先に)。行は「日付(なければ新着)：🍔【キャラ】何が；どこで」(collab_line)。
  - 件名に「コラボN」(今後の後・HS の前)。
- サイト:「🧸 ポケモン・サンリオ」タブ(大型セールの隣)。上にコラボ予定の枠(開始日・あと何日・未公式の印・出典リンク)、下に記事。カードには「🍔/🎁 キャラ名コラボ」ラベル(.tag.collab)。
- 2026-10-27:kw_regex が曲がった引用符(Domino’s など)に当たっていなかった不具合を修正(re.escape は ' をエスケープしないため、置換が効いていなかった)。
