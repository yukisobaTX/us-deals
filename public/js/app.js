'use strict';
// お得ノート:deals.json を読み、カテゴリ・種類・店で絞り込んで表示する。
// 見出しは外部の RSS 由来なので、innerHTML は使わず textContent で入れる。
(() => {
  const CATS = [
    { id: 'free', label: '🎁 無料でもらえる' },
    { id: 'all', label: 'すべて' },
    { id: 'grocery', label: 'スーパー' },
    { id: 'home', label: '雑貨・ホームセンター' },
    { id: 'food', label: 'レストラン・カフェ' },
    { id: 'online', label: 'ネット通販' },
    { id: 'other', label: 'その他' }
  ];
  const TYPES = [
    { id: 'free', label: '無料' }, { id: 'bogo', label: 'BOGO' }, { id: 'coupon', label: 'クーポン' },
    { id: 'gc', label: 'ギフトカード' }, { id: 'p50', label: '50%以上' }, { id: 'today', label: '期限が近い' }
  ];
  const DAY = 86400000;
  const state = { cat: 'free', types: new Set(), store: '', sort: 'new', q: '' };
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
    if (state.cat === 'free' && (!x.freebie || (x.freebie.when && daysLeft(x.freebie.when) < 0))) return false;
    if (!['all', 'free'].includes(state.cat) && !x.cats.includes(state.cat)) return false;
    for (const t of state.types) {
      if (t === 'p50' && !((x.pct || 0) >= 50)) return false;
      if (t === 'today' && !(x.expires && daysLeft(x.expires) <= 2)) return false;
      if (!['p50', 'today'].includes(t) && !x.types.includes(t)) return false;
    }
    if (state.store && !x.stores.includes(state.store)) return false;
    if (state.q && !(x.title + ' ' + (x.ja || '') + ' ' + x.stores.join(' ')).toLowerCase().includes(state.q)) return false;
    return true;
  }

  function sorted(list) {
    const s = list.slice();
    if (state.cat === 'free' && state.sort === 'new') {
      // 無料タブは「店頭 → クーポン」、それぞれ日付の近い順
      const k = (x) => (x.freebie.kind === 'store' ? '0' : '1') + (x.freebie.when || '9999');
      return s.sort((a, b) => k(a).localeCompare(k(b)));
    }
    if (state.sort === 'pct') s.sort((a, b) => (b.pct || 0) - (a.pct || 0) || b.posted.localeCompare(a.posted));
    else if (state.sort === 'exp') s.sort((a, b) => expOf(a).localeCompare(expOf(b)));
    else s.sort((a, b) => b.posted.localeCompare(a.posted));
    return s;
  }

  function card(x) {
    const sub = el('div', { className: 'sub' });
    if (Date.now() - Date.parse(x.firstSeen) < DAY) sub.append(el('span', { className: 'new', textContent: 'NEW' }));
    if (x.freebie) {
      const w = x.freebie.when ? (daysLeft(x.freebie.when) === 0 ? '今日' : md(x.freebie.when)) : '';
      sub.append(el('span', { className: 'tag free', textContent: (x.freebie.kind === 'store' ? '🏬 店頭' : '🎟 クーポン') + (w ? ' ' + w : '') }));
    }
    sub.append(el('span', { className: 'store', textContent: x.stores.join('・') || '—' }));
    for (const t of x.types) {
      const lab = { bogo: 'BOGO', coupon: 'クーポン', gc: 'ギフトカード' }[t];
      if (lab) sub.append(el('span', { className: 'tag', textContent: lab }));
    }
    if (x.pct) sub.append(el('span', { className: 'tag pct', textContent: `${x.pct}%OFF` }));
    if (x.expires && !(x.freebie && x.freebie.kind === 'store')) {
      const left = daysLeft(x.expires);
      sub.append(el('span', {
        className: 'tag exp' + (left <= 2 ? ' soon' : ''),
        textContent: left < 0 ? '期限切れ?' : left === 0 ? '今日まで' : `〜${md(x.expires)}`
      }));
    }
    sub.append(el('span', { textContent: `${md(new Date(Date.parse(x.posted)).toLocaleDateString('en-CA', { timeZone: 'America/Chicago' }))} 掲載・${x.source}` }));
    const href = /^https:\/\//.test(x.link) ? x.link : '#';
    return el('li', { className: 'card' + (x.freebie ? ' hot' : '') }, [
      el('a', { href, target: '_blank', rel: 'noopener noreferrer', textContent: x.ja || x.title }),
      x.ja ? el('div', { className: 'orig', textContent: x.title }) : null, sub
    ]);
  }

  function renderTabs() {
    const tabs = $('tabs');
    tabs.replaceChildren(...CATS.map((c) => {
      const n = c.id === 'all' ? items.length : c.id === 'free' ? items.filter((x) => x.freebie).length
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
    const pool = items.filter((x) => state.cat === 'all' || (state.cat === 'free' ? x.freebie : x.cats.includes(state.cat)));
    const cnt = new Map();
    for (const x of pool) for (const s of x.stores) cnt.set(s, (cnt.get(s) || 0) + 1);
    const sel = $('store');
    sel.replaceChildren(el('option', { value: '', textContent: 'すべての店' }),
      ...[...cnt].sort((a, b) => b[1] - a[1]).map(([s, n]) => el('option', { value: s, textContent: `${s}(${n})` })));
    sel.value = state.store;
  }

  function renderLinks() {
    const groups = links.groups.filter((g) => ['all', 'free'].includes(state.cat) || g.cat === state.cat);
    const label = Object.fromEntries(CATS.map((c) => [c.id, c.label]));
    $('linkbody').replaceChildren(...groups.flatMap((g) => [
      el('h3', { textContent: label[g.cat] || g.cat }),
      el('ul', {}, g.links.map((l) => el('li', {}, el('a', { href: l.url, target: '_blank', rel: 'noopener noreferrer', textContent: l.name }))))
    ]));
  }

  function render() {
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
      fetch('data/links.json' + v).then((r) => r.json()).catch(() => ({ groups: [] }))
    ]);
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
