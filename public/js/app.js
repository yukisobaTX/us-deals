'use strict';
// お得ノート:deals.json を読み、カテゴリ・種類・店で絞り込んで表示する。
// 見出しは外部の RSS 由来なので、innerHTML は使わず textContent で入れる。
(() => {
  const CATS = [
    { id: 'free', label: '🎁 無料でもらえる' },
    { id: 'family', label: '👨‍👩‍👧 家族のお出かけ' },
    { id: 'local', label: '📍 地元' },
    { id: 'event', label: '🛍 大型セール' },
    { id: 'all', label: 'すべて' },
    { id: 'grocery', label: 'スーパー' },
    { id: 'home', label: '雑貨・ホームセンター' },
    { id: 'food', label: 'レストラン・カフェ' },
    { id: 'online', label: 'ネット通販' },
    { id: 'other', label: 'その他' }
  ];
  const TYPES = [
    { id: 'free', label: '無料・BOGO' }, { id: 'bogo', label: 'BOGO' }, { id: 'coupon', label: 'クーポン' },
    { id: 'gc', label: 'ギフトカード' }, { id: 'p50', label: '50%以上' }, { id: 'today', label: '期限が近い' }
  ];
  const DAY = 86400000;
  const EVLAB = { 'black-friday': 'ブラックフライデー', 'cyber-monday': 'サイバーマンデー', 'prime-day': 'プライムデー',
    'amazon-spring': 'Amazon 春セール', 'target-circle': 'Target Circle Week', 'walmart-event': 'Walmart セール',
    'holiday-sale': '祝日セール', 'tax-free': '免税週末' };
  let calendar = [];
  const state = { cat: 'free', types: new Set(), store: '', sort: 'date', q: '' };
  let items = [];
  let links = { groups: [] };

  const $ = (id) => document.getElementById(id);
  const el = (tag, props = {}, kids = []) => {
    const n = document.createElement(tag);
    Object.assign(n, props);
    for (const k of [].concat(kids)) if (k != null) n.append(k);
    return n;
  };
  const ctToday = () => new Date().toLocaleDateString('en-CA', { timeZone: 'America/Chicago' });
  // 期限:見出しから読めたもの、なければ掲載日 + 7 日を目安
  const expOf = (x) => x.expires || new Date(Date.parse(x.posted) + 7 * DAY).toISOString().slice(0, 10);
  const daysLeft = (d) => Math.round((Date.parse(d + 'T12:00:00') - Date.parse(ctToday() + 'T12:00:00')) / DAY);
  const md = (d) => `${+d.slice(5, 7)}/${+d.slice(8, 10)}`;

  function match(x) {
    if (x.dup) return false;   // 別の情報源の同じ話題は1件にまとめる
    if (state.cat === 'free' && (!x.freebie || (x.freebie.when && daysLeft(x.freebie.when) < 0))) return false;
    if (state.cat === 'event' && !x.event) return false;
    if (state.cat === 'local' && !x.region) return false;
    if (state.cat === 'family' && (!x.family || (x.date && daysLeft(x.date) < 0))) return false;
    if (!['all', 'free', 'event', 'local', 'family'].includes(state.cat) && !x.cats.includes(state.cat)) return false;
    for (const t of state.types) {
      if (t === 'p50' && !((x.pct || 0) >= 50)) return false;
      if (t === 'today' && !(x.expires && daysLeft(x.expires) <= 2)) return false;
      if (!['p50', 'today'].includes(t) && !x.types.includes(t)) return false;
    }
    if (state.store && !x.stores.includes(state.store)) return false;
    if (state.q && !(x.title + ' ' + (x.ja || '') + ' ' + Object.values(x.sum || {}).join(' ') + ' ' + x.stores.join(' ')).toLowerCase().includes(state.q)) return false;
    return true;
  }

  function sorted(list) {
    const s = list.slice();
    if (state.sort === 'date') {
      // 日付順:配布日・期限の近い順(日付が読めないものは後ろに、新しい掲載順)
      return s.sort((a, b) => (a.date || '9999').localeCompare(b.date || '9999') || b.posted.localeCompare(a.posted));
    }
    if (state.sort === 'pct') s.sort((a, b) => (b.pct || 0) - (a.pct || 0) || b.posted.localeCompare(a.posted));
    else if (state.sort === 'exp') s.sort((a, b) => expOf(a).localeCompare(expOf(b)));
    else s.sort((a, b) => b.posted.localeCompare(a.posted));
    return s;
  }

  // 「店舗名:もらえるもの:日時:条件」(要約がなければ英語の見出し)
  function sumLine(x, href) {
    const a = (t) => el('a', { href, target: '_blank', rel: 'noopener noreferrer', textContent: t });
    const sm = x.sum;
    if (!sm || !sm.item) return el('div', { className: 'sumline' }, a(x.ja || x.title));
    let when = sm.when || '—';
    if (x.date && daysLeft(x.date) === 0 && !when.startsWith('〜')) when = '今日' + (when.includes(' ') ? ' ' + when.split(' ').slice(1).join(' ') : '');
    const store = sm.store || x.stores.filter((n) => n !== 'レストラン全般').slice(0, 2).join('・') || '—';
    return el('div', { className: 'sumline' }, [
      el('b', { textContent: store }), '：', a(sm.item), '：',
      el('span', { className: when.startsWith('今日') ? 'today' : '', textContent: when }), '：',
      el('span', { textContent: sm.cond || '—' })
    ]);
  }

  function card(x) {
    const sub = el('div', { className: 'sub' });
    if (Date.now() - Date.parse(x.firstSeen) < DAY) sub.append(el('span', { className: 'new', textContent: 'NEW' }));
    if (x.family) sub.append(el('span', { className: 'tag free', textContent: '👨‍👩‍👧 家族向け' + (x.localDate ? ' ' + md(x.localDate) : '') }));
    if (x.region) sub.append(el('span', { className: 'tag', textContent: '📍 ' + ({ 'College Station': 'カレッジステーション', Houston: 'ヒューストン' }[x.region] || x.region) }));
    if (x.event) sub.append(el('span', { className: 'tag ev', textContent: '🛍 ' + (EVLAB[x.event] || '大型セール') }));
    if (x.freebie) {
      const w = x.freebie.when ? (daysLeft(x.freebie.when) === 0 ? '今日' : md(x.freebie.when)) : '';
      sub.append(el('span', { className: 'tag free', textContent: (x.freebie.kind === 'store' ? '🏬 店頭' : '🎟 クーポン') + (w ? ' ' + w : '') }));
      if (x.freebie.bogo) sub.append(el('span', { className: 'tag free', textContent: '1つ買うと1つ無料' }));
    }
    sub.append(el('span', { className: 'store', textContent: x.stores.join('・') || '—' }));
    for (const t of x.types) {
      const lab = { bogo: 'BOGO', coupon: 'クーポン', gc: 'ギフトカード' }[t];
      if (t === 'bogo' && x.freebie && x.freebie.bogo) continue;
      if (lab) sub.append(el('span', { className: 'tag', textContent: lab }));
    }
    if (x.pct) sub.append(el('span', { className: 'tag pct', textContent: `${x.pct}%OFF` }));
    if (x.expires && !(x.freebie && x.freebie.kind === 'store') && !(x.sum && x.sum.when)) {
      const left = daysLeft(x.expires);
      sub.append(el('span', {
        className: 'tag exp' + (left <= 2 ? ' soon' : ''),
        textContent: left < 0 ? '期限切れ?' : left === 0 ? '今日まで' : `〜${md(x.expires)}`
      }));
    }
    sub.append(el('span', { textContent: `${md(new Date(Date.parse(x.posted)).toLocaleDateString('en-CA', { timeZone: 'America/Chicago' }))} 掲載・${x.source}` }));
    const href = /^https:\/\//.test(x.link) ? x.link : '#';
    const body = el('div', { className: 'body' }, [
      sumLine(x, href),
      (x.sum || x.ja) ? el('div', { className: 'orig', textContent: x.title }) : null, sub
    ]);
    // サムネ:配信元の画像を直接表示(保存はしない)。読めなければ枠ごと消す
    let thumb = null;
    if (x.thumb && /^https:\/\//.test(x.thumb)) {
      const img = el('img', { src: x.thumb, alt: '', loading: 'lazy', decoding: 'async', referrerPolicy: 'no-referrer' });
      img.onerror = () => { if (thumb.parentNode) thumb.parentNode.classList.remove('has-thumb'); thumb.remove(); };
      thumb = el('a', { className: 'thumb', href, target: '_blank', rel: 'noopener noreferrer', tabIndex: -1 }, img);
    }
    return el('li', { className: 'card' + (x.freebie ? ' hot' : '') + (thumb ? ' has-thumb' : '') }, [thumb, body]);
  }

  function renderTabs() {
    const tabs = $('tabs');
    tabs.replaceChildren(...CATS.map((c) => {
      const n = c.id === 'all' ? items.length : c.id === 'free' ? items.filter((x) => x.freebie).length : c.id === 'event' ? items.filter((x) => x.event).length
        : c.id === 'local' ? items.filter((x) => x.region && !x.dup).length
        : c.id === 'family' ? items.filter((x) => x.family && !x.dup && !(x.date && daysLeft(x.date) < 0)).length
        : items.filter((x) => x.cats.includes(c.id)).length;
      if (c.id === 'other' && !n) return null;
      const b = el('button', { type: 'button' }, [c.label, el('span', { className: 'n', textContent: n })]);
      b.setAttribute('aria-pressed', String(state.cat === c.id));
      b.onclick = () => { state.cat = c.id; state.store = ''; save(); render(); };
      return b;
    }).filter(Boolean));
  }

  function renderTypes() {
    $('types').replaceChildren(...TYPES.map((t) => {
      const b = el('button', { type: 'button', textContent: t.label });
      b.setAttribute('aria-pressed', String(state.types.has(t.id)));
      b.onclick = () => { state.types.has(t.id) ? state.types.delete(t.id) : state.types.add(t.id); render(); };
      return b;
    }));
  }

  function renderStores() {
    const pool = items.filter((x) => state.cat === 'all' || (state.cat === 'free' ? x.freebie : state.cat === 'event' ? x.event : state.cat === 'local' ? x.region : state.cat === 'family' ? x.family : x.cats.includes(state.cat)));
    const cnt = new Map();
    for (const x of pool) for (const s of x.stores) cnt.set(s, (cnt.get(s) || 0) + 1);
    const sel = $('store');
    sel.replaceChildren(el('option', { value: '', textContent: 'すべての店' }),
      ...[...cnt].sort((a, b) => b[1] - a[1]).map(([s, n]) => el('option', { value: s, textContent: `${s}(${n})` })));
    sel.value = state.store;
  }

  function renderLinks() {
    const groups = links.groups.filter((g) => ['all', 'free', 'event', 'local', 'family'].includes(state.cat) || g.cat === state.cat);
    const label = Object.fromEntries(CATS.map((c) => [c.id, c.label]));
    $('linkbody').replaceChildren(...groups.flatMap((g) => [
      el('h3', { textContent: label[g.cat] || g.cat }),
      el('ul', {}, g.links.map((l) => el('li', {}, el('a', { href: l.url, target: '_blank', rel: 'noopener noreferrer', textContent: l.name }))))
    ]));
  }

  function renderCalendar() {
    const box = document.getElementById('cal');
    if (state.cat !== 'event' || !calendar.length) { box.hidden = true; return; }
    box.hidden = false;
    const upcoming = calendar.filter((e) => !e.date || daysLeft(e.date) >= 0);
    box.replaceChildren(el('h2', { textContent: '大型セールの予定' }), el('ul', {}, upcoming.map((e) => {
      const left = e.date ? daysLeft(e.date) : null;
      const head = e.date ? `${md(e.date)}(${left === 0 ? '今日' : 'あと' + left + '日'})` : '例年';
      const li = el('li', {}, [el('b', { textContent: head + ' ' }), el('span', { textContent: e.name }),
        el('div', { className: 'note', textContent: e.note || '' })]);
      if (e.url && /^https:\/\//.test(e.url)) li.append(el('a', { href: e.url, target: '_blank', rel: 'noopener noreferrer', textContent: '公式' }));
      return li;
    })));
  }

  function render() {
    renderCalendar();
    renderTabs(); renderTypes(); renderStores(); renderLinks();
    const list = sorted(items.filter(match));
    $('count').textContent = `${list.length} 件`;
    $('list').replaceChildren(...(list.length ? list.map(card) : [el('li', { className: 'empty', textContent: '該当する情報はありません。' })]));
  }

  function save() { try { localStorage.setItem('deals.cat', state.cat); } catch (e) { /* 保存できなくても動く */ } }

  async function load() {
    try { state.cat = localStorage.getItem('deals.cat') || 'free'; if (!CATS.some((c) => c.id === state.cat)) state.cat = 'free'; } catch (e) { /* noop */ }
    const v = '?v=' + Date.now();
    const [d, l] = await Promise.all([
      fetch('data/deals.json' + v).then((r) => r.json()),
      fetch('data/links.json' + v).then((r) => r.json()).catch(() => ({ groups: [] })),
      fetch('data/events.json' + v).then((r) => r.json()).catch(() => ({ events: [] }))
    ]).then((r) => { calendar = (r[2].events || []); return r; });
    items = d.items || [];
    links = l;
    const up = new Date(Date.parse(d.updated)).toLocaleString('ja-JP', { timeZone: 'America/Chicago', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    $('meta').textContent = `テキサス生活のお得情報・${items.length} 件・更新 ${up}(CT)` + (d.errors && d.errors.length ? ' ⚠️ 一部取得失敗' : '');
    render();
  }

  $('store').onchange = (e) => { state.store = e.target.value; render(); };
  $('sort').onchange = (e) => { state.sort = e.target.value; render(); };
  $('q').oninput = (e) => { state.q = e.target.value.trim().toLowerCase(); render(); };
  load().catch(() => { $('meta').textContent = 'データを読み込めませんでした。'; });
})();
