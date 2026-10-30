'use strict';
/* Dune: Awakening Save Editor — UI. Talks to the local Python server (see dune_editor/server.py). */

const S = {
  st: null, tab: 'overview',
  skills: null, pendingRanks: {}, cls: 'Trooper', skillFilter: { q: '', kind: 'all' },
  spec: null, pendingLevels: {}, pendingKs: null,
  recipes: null, sel: {}, rf: { q: '', kind: 'all', cat: 'all' },
  building: null, bPending: null, cust: null, inv: null, backups: null,
};
const $ = id => document.getElementById(id);
const h = (tag, attrs, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') e.className = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (v === true) e.setAttribute(k, ''); else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
};
const fmt = n => (n == null ? '—' : Number(n).toLocaleString('en-US'));
const svgNS = 'http://www.w3.org/2000/svg';
const svg = (tag, attrs) => { const e = document.createElementNS(svgNS, tag); for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v); return e; };

async function api(path, body) {
  const opt = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Dune-Editor': '1' }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const j = await r.json().catch(() => ({ error: 'bad response' }));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
let toastTimer;
function toast(msg, err) {
  const t = $('toast'); t.textContent = msg; t.className = 'on' + (err ? ' err' : '');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.className = '', err ? 6000 : 2600);
}
const guard = fn => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message, true); } };
function ask(title, body, okLabel = 'Continue') {
  return new Promise(res => {
    const d = $('dlg'); $('dlgBody').replaceChildren(h('h3', { style: 'margin:0 0 8px' }, title), ...[].concat(body));
    const a = $('dlgActions');
    a.replaceChildren(h('button', { class: 'btn', onclick: () => { d.close(); res(false); } }, 'Cancel'),
      h('button', { class: 'btn primary', onclick: () => { d.close(); res(true); } }, okLabel));
    d.showModal();
  });
}

/* ------------------------------------------------------------------ icons */
const ICON_SOLARI = '<svg viewBox="0 0 24 24"><rect x="2.5" y="2.5" width="19" height="19" rx="3" fill="none" stroke="#a4501a" stroke-width="1.8"/><text x="12" y="17" text-anchor="middle" font-size="14" font-weight="700" fill="#a4501a" font-family="Segoe UI,sans-serif">S</text></svg>';
const ICON_SCRIPT = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9.5" fill="#e3b488" stroke="#a4501a" stroke-width="1.8"/><circle cx="12" cy="12" r="5.5" fill="none" stroke="#a4501a" stroke-width="1.3"/><path d="M9 12h6M12 9v6" stroke="#a4501a" stroke-width="1.3"/></svg>';

/* ------------------------------------------------------------------ state / header */
async function refreshState() {
  S.st = await api('/api/state');
  if (!S.st.open && S.st.saves.length === 1) { S.st = await api('/api/open', { path: S.st.saves[0].path }); }
  renderChrome();
}
const TABS = [['overview', 'Overview'], ['skills', 'Skills'], ['spec', 'Specializations'], ['recipes', 'Recipes'], ['building', 'Building'], ['custom', 'Skins & Swatches'], ['inventory', 'Inventory'], ['backups', 'Backups']];

function renderChrome() {
  const st = S.st, ov = st.overview;
  $('whoName').textContent = ov ? ov.name : '—';
  $('whoId').textContent = ov ? ov.funcom_id : 'no save open';
  $('tabs').replaceChildren(...TABS.map(([id, label]) => h('button', {
    role: 'tab', 'aria-selected': String(S.tab === id), disabled: !ov && id !== 'overview' && id !== 'backups',
    onclick: () => { S.tab = id; renderChrome(); render(); },
  }, label)));
  const w = $('wallet'); w.replaceChildren();
  if (ov) {
    const sol = ov.currency.find(c => c.id === 0), scr = ov.currency.find(c => c.id === 1);
    const cur = (c, icon) => { const d = h('div', { class: 'cur', title: c.label }, fmt(c.balance)); const i = h('span'); i.innerHTML = icon; d.append(i.firstChild); return d; };
    w.append(cur(sol, ICON_SOLARI), cur(scr, ICON_SCRIPT), h('div', { class: 'lvl' }, 'LVL', h('b', {}, String(ov.level)), h('i')));
  }
  $('barSave').textContent = st.open || 'No save open';
  $('barRun').hidden = !st.running.length;
  $('barDirty').textContent = st.dirty ? 'Edits staged — not yet written to the game' : '';
  $('btnWrite').disabled = !st.dirty; $('btnDiscard').disabled = !st.dirty;
}

$('btnWrite').onclick = guard(async () => {
  if (!await ask('Write changes to the game?', [
    h('p', {}, 'This replaces your save file. A full backup of the save folder is made first (see the Backups tab).'),
    h('p', { class: 'warn' }, 'Dune: Awakening must be completely closed.')], 'Write now')) return;
  const r = await api('/api/write', {});
  S.st = r.state; S.skills = S.spec = S.recipes = S.building = S.cust = S.inv = null; S.pendingRanks = {}; S.pendingLevels = {}; S.pendingKs = null;
  renderChrome(); render();
  toast('Saved. Backup: ' + r.result.backup);
});
$('btnDiscard').onclick = guard(async () => {
  if (!await ask('Discard staged edits?', h('p', {}, 'Everything you changed since opening the save (or last writing) is dropped.'), 'Discard')) return;
  S.st = await api('/api/discard', {}); S.skills = S.spec = S.recipes = S.building = S.cust = S.inv = null; S.pendingRanks = {}; S.pendingLevels = {}; S.pendingKs = null; S.sel = {};
  renderChrome(); render(); toast('Edits discarded');
});
setInterval(guard(async () => { if (document.visibilityState === 'visible') { const s = await api('/api/state'); S.st.running = s.running; $('barRun').hidden = !s.running.length; } }), 8000);

/* ------------------------------------------------------------------ router */
async function render() {
  const v = $('view');
  try {
    if (!S.st.open && S.tab !== 'backups') return renderPicker(v);
    ({ overview: renderOverview, skills: renderSkills, spec: renderSpec, recipes: renderRecipes, building: renderBuilding, custom: renderCustom, inventory: renderInventory, backups: renderBackups })[S.tab](v);
  } catch (e) { v.replaceChildren(h('div', { class: 'panel' }, 'Error: ' + e.message)); }
}

function renderPicker(v) {
  const saves = S.st.saves;
  v.replaceChildren(h('h2', { class: 'sect' }, 'Choose a save'),
    saves.length ? saves.map(s => h('div', { class: 'save-card' },
      h('div', {}, h('div', {}, h('code', {}, s.path)), h('div', { class: 'muted' }, `Account ${s.account} · ${(s.size / 1024).toFixed(0)} KB · modified ${s.modified.replace('T', ' ')}`)),
      h('button', { class: 'btn primary', onclick: guard(async () => { S.st = await api('/api/open', { path: s.path }); renderChrome(); render(); }) }, 'Open')))
      : h('div', { class: 'panel' }, 'No Dune: Awakening save was found under %LOCALAPPDATA%\\DuneSandbox\\Saved\\Cloud\\PlayerClientStorage. Start the game once in single-player, then reload this page.'));
}

/* ------------------------------------------------------------------ overview (dashboard) */
const pct = ([a, b]) => (b ? Math.max(0, Math.min(100, Math.round(100 * a / b))) : 0);
const meter = p => h('div', { class: 'meter' }, h('i', { style: `width:${p}%` }));
const icon = svgText => { const s = h('span', { class: 'ico' }); s.innerHTML = svgText; return s; };
async function renderOverview(v) {
  if (!S.skills) S.skills = await api('/api/skills');
  const [sum, chg] = await Promise.all([api('/api/summary'), api('/api/changes')]);
  const ov = S.st.overview, sk = S.skills.state;
  const sol = ov.currency.find(c => c.id === 0).balance, scr = ov.currency.find(c => c.id === 1).balance;
  const inp = (id, val, max = 2000000000) => h('input', { type: 'number', id, value: val, min: 0, max, step: 1 });
  const maxBtn = (id, max) => h('button', { class: 'btn sm', type: 'button', title: `Set to the limit (${fmt(max)})`, onclick: () => { $(id).value = max; } }, 'Max');
  const go = tab => { S.tab = tab; renderChrome(); render(); };

  const stat = (label, ic, id, val, max) => h('label', { class: 'stat' }, h('span', { class: 'lab' }, ic ? icon(ic) : null, label), h('span', { class: 'fld' }, inp(id, val, max), maxBtn(id, max)));
  const hero = h('div', { class: 'panel hero' },
    h('div', { class: 'medal', title: 'Character level' }, h('div', { class: 'in' }, h('small', {}, 'LVL'), h('b', {}, String(ov.level)))),
    h('div', { class: 'who' }, h('div', { class: 'big' }, ov.name), h('div', { class: 'muted' }, ov.funcom_id),
      h('div', { class: 'note', style: 'margin-top:6px' }, `${fmt(sum.items)} items carried`)),
    h('div', { class: 'stats' }, stat('Solari', ICON_SOLARI, 'inSol', sol, 2000000000), stat('House Script', ICON_SCRIPT, 'inScr', scr, 2000000000), stat('Tech points', null, 'inTech', ov.tech_points ?? 0, 1000000)),
    h('button', { class: 'btn primary', onclick: guard(async () => {
      await api('/api/currency', { balances: { 0: +$('inSol').value, 1: +$('inScr').value } });
      await api('/api/tech', { value: +$('inTech').value });
      await refreshState(); render(); toast('Staged. Use “Write to game” to save.');
    }) }, 'Apply wallet'));

  const tiles = [['building', 'Building sets', sum.building, 'learned'], ['custom', 'Skins & swatches', sum.skins, 'unlocked'], ['recipes', 'Recipes', sum.recipes, 'known'],
    ['skills', 'Skill nodes', sum.skills, 'ranked'], ['spec', 'Specializations', sum.spec, 'of max track levels'], ['inventory', 'Backpack', sum.backpack, 'slots in use']];
  const grid = h('div', { class: 'tiles' }, tiles.map(([tab, name, val, unit]) => h('button', { class: 'tile', onclick: () => go(tab), 'aria-label': `Open ${name}` },
    h('span', { class: 'tn' }, name), h('span', { class: 'tv' }, fmt(val[0]), h('small', {}, ' / ' + fmt(val[1]))), meter(pct(val)), h('span', { class: 'tu' }, `${pct(val)}% ${unit}`))));

  const total = chg.groups.reduce((n, g) => n + g.lines.length + g.more, 0);
  const changes = h('div', { class: 'panel changes' },
    h('div', { class: 'row' }, h('div', {}, h('b', {}, total ? `${total} staged change${total > 1 ? 's' : ''}` : 'No staged changes'),
      h('div', { class: 'note' }, total ? 'Compared with the save as it was when opened. Nothing is in your game until you write it.' : 'Edits you make on any tab will be listed here, compared with your current save.')),
      h('span', { style: 'margin-left:auto' }),
      total ? [h('button', { class: 'btn sm', onclick: () => $('btnDiscard').click() }, 'Discard all'), h('button', { class: 'btn sm primary', onclick: () => $('btnWrite').click() }, 'Write to game')] : null),
    ...chg.groups.map(g => h('div', { class: 'cg' }, h('div', { class: 'cgh' }, g.area, h('span', { class: 'count' }, String(g.lines.length + g.more))),
      h('ul', {}, g.lines.map(l => h('li', {}, l)), g.more ? h('li', { class: 'muted' }, `…and ${g.more} more`) : null))));

  const level = h('div', { class: 'panel' }, h('h3', { class: 'ph' }, 'Character level & skill points'),
    h('div', { class: 'fields' },
      h('label', { class: 'f' }, 'Total skill points', inp('inTot', sk.total_points, 5000)),
      h('label', { class: 'f' }, 'Unspent skill points', inp('inUns', sk.unspent_points, 5000)),
      h('label', { class: 'f' }, 'Total XP earned', inp('inXp', sk.total_xp))),
    h('div', { class: 'row', style: 'margin-top:14px' }, h('button', { class: 'btn primary', onclick: guard(async () => {
      await api('/api/skills', { total_points: +$('inTot').value, unspent_points: +$('inUns').value, total_xp: +$('inXp').value });
      S.skills = null; await refreshState(); render(); toast('Staged. Use “Write to game” to save.');
    }) }, 'Apply'), h('span', { class: 'note', style: 'flex:1;min-width:200px' }, `Level = total skill points + 1 (now LVL ${sk.total_points + 1}). Unspent points are separate from skill ranks.`)));
  const save = h('details', { class: 'panel savebox' }, h('summary', {}, 'Save file'), h('dl', { class: 'kv', style: 'margin-top:12px' },
    h('dt', {}, 'File'), h('dd', {}, S.st.open), h('dt', {}, 'Character'), h('dd', {}, `${ov.name} (${ov.funcom_id})`), h('dt', {}, 'Steam ID'), h('dd', {}, ov.platform_id)));

  v.replaceChildren(hero, h('h2', { class: 'sect' }, 'Your collection'), grid, h('h2', { class: 'sect' }, 'Pending changes'),
    h('div', { class: 'dash' }, changes, h('div', { class: 'stack' }, level, save)));
}

/* ------------------------------------------------------------------ skills */
const GLYPH = { Trooper: 'T', Mentat: 'M', Planetologist: 'P', BeneGesserit: 'BG', Swordmaster: 'S' };
const rankOf = tag => (tag in S.pendingRanks ? S.pendingRanks[tag] : (S.skills.state.ranks[tag] || 0));
function setRank(n, r) {
  const saved = S.skills.state.ranks[n.tag] || 0;
  if (r === saved) delete S.pendingRanks[n.tag]; else S.pendingRanks[n.tag] = r;
}
const pendingCount = () => Object.keys(S.pendingRanks).length;

async function renderSkills(v) {
  if (!S.skills) S.skills = await api('/api/skills');
  const cat = S.skills.catalog, nodes = cat.nodes;
  const cls = cat.classes.find(c => c.id === S.cls) || cat.classes[0];
  const mine = nodes.filter(n => n.class === cls.id);
  const bar = h('div', { class: 'stickybar row' },
    h('span', {}, pendingCount() ? `${pendingCount()} skill change(s) pending` : 'Click a node to raise its rank; it wraps back to 0 after the maximum.'),
    h('span', { style: 'margin-left:auto' }),
    h('button', { class: 'btn', onclick: () => { mine.forEach(n => setRank(n, n.max)); renderSkills(v); } }, `Max ${cls.label}`),
    h('button', { class: 'btn', onclick: () => { mine.forEach(n => setRank(n, 0)); renderSkills(v); } }, `Clear ${cls.label}`),
    h('button', { class: 'btn', disabled: !pendingCount(), onclick: () => { S.pendingRanks = {}; renderSkills(v); } }, 'Revert'),
    h('button', { class: 'btn primary', disabled: !pendingCount(), onclick: guard(async () => {
      await api('/api/skills', { ranks: S.pendingRanks }); S.pendingRanks = {}; S.skills = null; await refreshState(); render(); toast('Staged. Use “Write to game” to save.');
    }) }, 'Apply skill changes'));

  const classbar = h('div', { class: 'classbar' },
    ...cat.classes.map(c => h('button', { class: 'class-btn', 'aria-pressed': String(c.id === cls.id), title: c.label, onclick: () => { S.cls = c.id; renderSkills(v); } },
      h('div', { class: 'dia' }, h('span', {}, GLYPH[c.id])))),
    h('span', { class: 'class-title' }, cls.label),
    h('div', { class: 'sp-badge' }, h('small', {}, 'Skill points'), h('b', {}, String(S.skills.state.unspent_points))));

  const gates = mine.filter(n => n.role === 'gate').sort((a, b) => a.order - b.order);
  const gateRow = h('div', { class: 'tier-gates' }, h('span', { class: 'note' }, 'Tier unlocks:'),
    ...gates.map(g => h('button', { class: 'gate' + (rankOf(g.tag) ? ' on' : ''), title: g.tag,
      onclick: () => { setRank(g, (rankOf(g.tag) + 1) % (g.max + 1)); renderSkills(v); } }, g.name.replace(/^.* tier/, 'Tier') + (rankOf(g.tag) ? ' ✓' : ''))));

  const trees = h('div', { class: 'trees' }, ...cls.trees.map(t => buildTree(t, mine, v)));

  // abilities / perks / spice (not tied to a class in the data)
  const f = S.skillFilter;
  const loose = nodes.filter(n => !n.class && n.kind !== 'Science').filter(n => (f.kind === 'all' || n.kind === f.kind) &&
    (!f.q || (n.name + ' ' + n.tag + ' ' + n.short).toLowerCase().includes(f.q.toLowerCase())));
  const cards = h('div', { class: 'skill-cards' }, ...loose.map(n => skillCard(n, v)));
  const looseHead = h('div', { class: 'row' },
    h('div', { class: 'chips' }, ...['all', 'Ability', 'Perk', 'Spice'].map(k => h('button', { class: 'chip', 'aria-pressed': String(f.kind === k), onclick: () => { f.kind = k; renderSkills(v); } },
      k === 'all' ? 'All' : k === 'Spice' ? 'Spice techniques' : k === 'Ability' ? 'Abilities' : k + 's'))),
    h('input', { type: 'search', placeholder: 'Search abilities and perks…', value: f.q, oninput: e => { f.q = e.target.value; clearTimeout(S._ft); S._ft = setTimeout(() => { renderSkills(v); const i = v.querySelector('input[type=search]'); i.focus(); i.setSelectionRange(f.q.length, f.q.length); }, 250); } }),
    h('button', { class: 'btn sm', onclick: () => { loose.forEach(n => setRank(n, n.max)); renderSkills(v); } }, `Max these ${loose.length}`),
    h('button', { class: 'btn sm', onclick: () => { loose.forEach(n => setRank(n, 0)); renderSkills(v); } }, 'Clear these'));

  v.replaceChildren(bar, classbar, gateRow, trees,
    h('div', { class: 'note warnbox' }, `Maximum ranks are my best reading of the game (keys and perks 1, attributes and abilities ${cat.max_rank.Attribute}). `,
      'Skill points are counted separately (Overview tab).'),
    h('h2', { class: 'sect' }, 'Abilities, perks & spice techniques (shared across classes)'), looseHead, h('div', { style: 'height:10px' }), cards);
}

function buildTree(t, mine, v) {
  const nodes = mine.filter(n => n.tree === t.id);
  const cap = nodes.find(n => n.role === 'capstone');
  const attrs = nodes.filter(n => n.role === 'node').sort((a, b) => a.order - b.order);
  const pattern = [2, 1, 2, 1, 2, 1, 2, 1];
  const pos = []; let left = attrs.length, y = 130, ri = 0;
  while (left > 0) {
    const k = Math.min(pattern[ri % pattern.length], left);
    const xs = k === 1 ? [150] : [88, 212];
    for (let i = 0; i < k; i++) pos.push({ x: xs[i], y, row: ri });
    left -= k; y += 78; ri++;
  }
  const H = Math.max(160, y - 20);
  const wrap = h('div', { class: 'tree' }, h('h3', {}, t.label));
  const canvas = h('div', { class: 'tree-canvas', style: `height:${H}px` });
  const s = svg('svg', { width: 300, height: H, viewBox: `0 0 300 ${H}` });
  const pts = [];
  if (cap) pts.push({ n: cap, x: 150, y: 50, row: -1 });
  attrs.forEach((n, i) => pts.push({ n, ...pos[i] }));
  for (const a of pts) for (const b of pts) {
    if (b.row === a.row + 1 && Math.abs(a.x - b.x) <= 130)
      s.append(svg('line', { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: rankOf(a.n.tag) && rankOf(b.n.tag) ? 'on' : '' }));
  }
  canvas.append(s);
  for (const p of pts) {
    const n = p.n, r = rankOf(n.tag), cap_ = n.role === 'capstone';
    const b = h('button', { class: 'node' + (r ? ' on' : '') + (cap_ ? ' cap round' : ''), style: `left:${p.x}px;top:${p.y}px`,
      title: `${n.name}\n${n.tag}\nRank ${r}/${n.max}`, onclick: () => { setRank(n, (r + 1) % (n.max + 1)); renderSkills(v); } },
      h('div', { class: 'dia' }), h('div', { class: 'lab' }, cap_ ? '★' : String(n.order)),
      h('div', { class: 'pips' }, ...Array.from({ length: n.max }, (_, i) => h('i', { class: i < r ? 'f' : '' }))));
    canvas.append(b);
  }
  wrap.append(canvas);
  if (!attrs.length) wrap.append(h('p', { class: 'note', style: 'text-align:center' }, 'No attribute nodes are stored for this tree; its abilities are in the shared list below.'));
  return wrap;
}

function skillCard(n, v) {
  const r = rankOf(n.tag);
  return h('div', { class: 'skill-card' + (r ? ' on' : '') },
    h('div', { class: 'nm' }, n.name),
    h('div', { class: 'rankbtn' }, ...Array.from({ length: n.max + 1 }, (_, i) => h('button', { class: i === r ? 'sel' : '', onclick: () => { setRank(n, i); renderSkills(v); } }, String(i)))),
    h('div', { class: 'tg' }, n.tag + (n.tag in S.pendingRanks ? '  · pending' : '')),
    n.short ? h('div', { class: 'ds' }, n.short) : null);
}

/* ------------------------------------------------------------------ specializations */
const TRACK_ORDER = ['Crafting', 'Gathering', 'Exploration', 'Combat', 'Sabotage'];
async function renderSpec(v) {
  if (!S.spec) { S.spec = await api('/api/spec'); S.pendingKs = null; S.pendingLevels = {}; }
  const sp = S.spec;
  if (!S.pendingKs) S.pendingKs = new Set(sp.keystones.filter(k => k.owned).map(k => k.name));
  const lvOf = t => (t.track in S.pendingLevels ? S.pendingLevels[t.track] : t.level);
  const dirty = Object.keys(S.pendingLevels).length || sp.keystones.some(k => k.owned !== S.pendingKs.has(k.name));
  const bar = h('div', { class: 'stickybar row' },
    h('span', {}, dirty ? 'Specialization changes pending' : 'Set a track level and click traits to own them.'), h('span', { style: 'margin-left:auto' }),
    h('button', { class: 'btn', disabled: !dirty, onclick: () => { S.spec = null; renderSpec(v); } }, 'Revert'),
    h('button', { class: 'btn primary', disabled: !dirty, onclick: guard(async () => {
      await api('/api/spec', { levels: S.pendingLevels, keystones: [...S.pendingKs] }); S.spec = null; await refreshState(); render(); toast('Staged. Use “Write to game” to save.');
    }) }, 'Apply specialization changes'));
  const rows = [...sp.tracks].sort((a, b) => TRACK_ORDER.indexOf(a.name) - TRACK_ORDER.indexOf(b.name)).map(t => {
    const L = lvOf(t), ks = sp.keystones.filter(k => k.track === t.name).sort((a, b) => a.level - b.level);
    const head = h('div', { class: 'track-head' }, h('div', { class: 'tn' }, t.name),
      h('div', { class: 'tl' }, h('small', {}, 'LVL '), String(Math.floor(L))),
      h('input', { type: 'range', min: 0, max: sp.max_level, value: Math.floor(L), 'aria-label': t.name + ' level',
        oninput: e => { S.pendingLevels[t.track] = +e.target.value; renderSpec(v); } }),
      h('div', { class: 'note' }, `${ks.filter(k => S.pendingKs.has(k.name)).length}/${ks.length} traits`),
      h('div', { class: 'row', style: 'margin-top:6px' },
        h('button', { class: 'btn sm', onclick: () => { ks.forEach(k => S.pendingKs.add(k.name)); renderSpec(v); } }, 'All'),
        h('button', { class: 'btn sm', onclick: () => { ks.filter(k => k.level <= L).forEach(k => S.pendingKs.add(k.name)); renderSpec(v); } }, 'Up to level'),
        h('button', { class: 'btn sm', onclick: () => { ks.forEach(k => S.pendingKs.delete(k.name)); renderSpec(v); } }, 'None')),
      t.confirmed ? null : h('div', { class: 'unconf', title: 'Track 1 is confirmed as Crafting. Tracks 2-5 follow the in-game row order, which I could not verify from the save.' }, `track #${t.track} · mapping unverified`));
    const strip = h('div', { class: 'ks-strip' }, ...ks.map(k => h('div', { class: 'ks' + (S.pendingKs.has(k.name) ? ' owned' : '') + (k.level > L ? ' locked' : ''), title: k.name,
      onclick: () => { S.pendingKs.has(k.name) ? S.pendingKs.delete(k.name) : S.pendingKs.add(k.name); renderSpec(v); } },
      h('span', { class: 'lv' }, h('b', {}, k.level ? String(k.level) : '·')), k.base.replace(/([a-z])([A-Z])/g, '$1 $2'))));
    return h('div', { class: 'track' }, head, strip);
  });
  const sx = v.scrollTop; const y = window.scrollY;
  v.replaceChildren(bar, ...rows, h('div', { class: 'note warnbox' }, 'Level sets the track XP from the game’s own XP curve (levels 0–100). Traits show the level they unlock at. Tracks 2–5 are labelled from the in-game order and could not be verified from the save alone.'));
  window.scrollTo(0, y);
}

/* ------------------------------------------------------------------ recipes */
const gradeCol = g => (g ? `var(--g${g})` : '#7a6c5a');
async function renderRecipes(v) {
  if (!S.recipes) { S.recipes = await api('/api/recipes'); }
  const R = S.recipes, f = S.rf;
  const have = {};
  R.known.forEach(k => { (have[k.id.toLowerCase()] ||= {})[k.grade] = k.count; });
  const q = f.q.trim().toLowerCase();
  const vis = R.catalog.filter(r => (f.kind === 'all' || r.kind === f.kind) && (f.cat === 'all' || r.cat === f.cat) &&
    (!q || (r.name + ' ' + r.short + ' ' + r.id).toLowerCase().includes(q)));
  const cats = ['all', ...new Set(R.catalog.filter(r => f.kind === 'all' || r.kind === f.kind).map(r => r.cat))].sort();
  const n = Object.keys(S.sel).length;
  const setSel = (r, on) => { if (on) S.sel[r.id] ||= { grade: 5, count: Math.max(1, (have[r.id.toLowerCase()] || {})[5] || 1) }; else delete S.sel[r.id]; };
  const chips = (vals, key, lab) => h('div', { class: 'chips' }, ...vals.map(x => h('button', { class: 'chip', 'aria-pressed': String(f[key] === x), onclick: () => { f[key] = x; renderRecipes(v); } }, lab(x))));
  const bar = h('div', { class: 'stickybar' },
    h('div', { class: 'row' },
      h('input', { type: 'search', placeholder: 'Search name, description or ID…', value: f.q, style: 'flex:1;min-width:200px',
        oninput: e => { f.q = e.target.value; clearTimeout(S._rt); S._rt = setTimeout(() => { renderRecipes(v); const i = v.querySelector('input[type=search]'); i.focus(); i.setSelectionRange(f.q.length, f.q.length); }, 250); } }),
      chips(['all', 'unique', 'augment'], 'kind', x => ({ all: 'All', unique: 'Weapons & armor', augment: 'Augmentations' }[x])),
      chips(cats, 'cat', x => x === 'all' ? 'All types' : x)),
    h('div', { class: 'row', style: 'margin-top:8px' },
      h('span', { class: 'muted' }, `${n} selected · ${vis.length} shown of ${R.catalog.length}`),
      h('span', { style: 'margin-left:auto' }),
      h('label', { class: 'row' }, 'Grade', h('select', { id: 'bulkG' }, h('option', { value: '' }, '—'), [5, 4, 3, 2, 1].map(g => h('option', { value: g }, g)))),
      h('label', { class: 'row' }, 'Know ×', h('input', { type: 'number', id: 'bulkC', min: 1, max: 99, style: 'width:70px' })),
      h('button', { class: 'btn sm', onclick: () => { const g = $('bulkG').value, c = $('bulkC').value; Object.values(S.sel).forEach(s => { if (g) s.grade = +g; if (c) s.count = Math.max(1, Math.min(99, +c)); }); renderRecipes(v); } }, 'Set on all selected'),
      h('button', { class: 'btn sm', onclick: () => { vis.forEach(r => setSel(r, true)); renderRecipes(v); } }, 'Select all shown'),
      h('button', { class: 'btn sm', onclick: () => { S.sel = {}; renderRecipes(v); } }, 'Clear'),
      h('button', { class: 'btn primary', disabled: !n, onclick: guard(async () => {
        const items = Object.entries(S.sel).map(([id, s]) => ({ id, grade: s.grade, count: s.count }));
        const r = await api('/api/recipes', { items }); S.sel = {}; S.recipes = null; await refreshState(); render();
        toast(`Staged: ${r.added} added, ${r.changed} changed. Use “Write to game” to save.`);
      }) }, n ? `Apply ${n} recipe(s)` : 'Apply')));
  const card = r => {
    const s = S.sel[r.id], hv = have[r.id.toLowerCase()];
    const hvText = hv ? 'You know: ' + Object.entries(hv).sort((a, b) => b[0] - a[0]).map(([g, c]) => `${+g ? 'Grade ' + g : 'Ungraded'} ×${c}`).join(', ') : '';
    const el = h('div', { class: 'rc' + (s ? ' sel' : ''), onclick: e => { if (e.target.closest('details,code,summary,select,input,.opts')) return; setSel(r, !S.sel[r.id]); renderRecipes(v); } },
      h('input', { type: 'checkbox', checked: !!s, 'aria-label': 'Select ' + r.name, onclick: e => { e.stopPropagation(); setSel(r, e.target.checked); renderRecipes(v); } }),
      h('div', {}, h('div', { class: 'row', style: 'gap:8px' }, h('span', { class: 'nm', title: r.id }, r.name),
          s ? h('span', { class: 'badge', style: `background:${gradeCol(s.grade)}` }, `Grade ${s.grade} ×${s.count}`) : null,
          h('span', { class: 'meta' }, r.cat + (r.kind === 'unique' && r.pool ? ` · drops in Grade ${r.pool} pool` : '')),
          hvText ? h('span', { class: 'have' }, hvText) : null),
        r.short ? h('div', { class: 'ds' }, r.short) : null,
        r.long ? h('details', {}, h('summary', { class: 'meta' }, 'More'), h('div', { class: 'meta', style: 'white-space:pre-line;margin-top:4px' }, r.long)) : null,
        null),
      h('div', { class: 'opts' + (s ? '' : ' off') },
        h('label', {}, 'Grade', h('select', { disabled: !s, onchange: e => { S.sel[r.id].grade = +e.target.value; renderRecipes(v); } }, [5, 4, 3, 2, 1].map(g => h('option', { value: g, selected: s && s.grade === g }, g)))),
        h('label', {}, 'Know ×', h('input', { type: 'number', min: 1, max: 99, value: s ? s.count : 1, disabled: !s, onchange: e => { S.sel[r.id].count = Math.max(1, Math.min(99, +e.target.value || 1)); renderRecipes(v); } }))));
    return el;
  };
  const y = window.scrollY;
  v.replaceChildren(bar,
    aboutBox('Grade is the recipe’s in-game “Grade Level”. “Know ×” is the total number of times you can craft it at that grade. ',
      `Your save holds ${R.known.length} known-recipe entries; this list covers the Tier 6 weapon, armor, stillsuit and augmentation schematics.`),
    ...[['unique', 'Weapons, armor & stillsuits'], ['augment', 'Augmentations']].map(([k, title]) => {
      const rows = vis.filter(r => r.kind === k);
      return rows.length ? h('section', {}, h('h2', { class: 'sect' }, `${title} · ${rows.length}`), ...rows.map(card)) : null;
    }));
  window.scrollTo(0, y);
}

/* ------------------------------------------------------------------ catalogue tiles (building, skins) */
const gMeter = (have, total) => h('span', { class: 'gm' }, h('span', { class: 'meter' }, h('i', { style: `width:${total ? Math.round(100 * have / total) : 0}%` })), h('b', {}, `${have} / ${total}`));
const aboutBox = text => h('details', { class: 'hint hintbox' }, h('summary', {}, 'About this tab'), h('p', {}, text));
function ctile(on, title, kids, toggle) {
  const t = h('div', { class: 'ctile' + (on ? ' on' : ''), role: 'checkbox', 'aria-checked': String(on), tabindex: '0', title, onclick: e => { if (!e.target.closest('details')) toggle(); } },
    h('span', { class: 'ck' }, on ? '\u2713' : ''), h('div', { class: 'ct' }, ...kids));
  t.addEventListener('keydown', e => { if (e.target === t && (e.key === ' ' || e.key === 'Enter')) { e.preventDefault(); toggle(); } });
  return t;
}
function groupBlock(title, entries, isOn, setAll, tile, verbs) {
  const have = entries.filter(isOn).length;
  return h('section', { class: 'group' }, h('div', { class: 'ghead' }, h('h3', {}, title), gMeter(have, entries.length), h('span', { style: 'margin-left:auto' }),
    h('button', { class: 'btn sm', disabled: have === entries.length, onclick: () => setAll(entries, true) }, verbs[0]), h('button', { class: 'btn sm', disabled: !have, onclick: () => setAll(entries, false) }, verbs[1])),
    h('div', { class: 'tgrid' }, entries.map(tile)));
}

/* ------------------------------------------------------------------ building */
const bGroup = id => (id.startsWith('MTX_') ? 'Store & event bundles' : /Set$/.test(id) ? 'Structure sets'
  : /Fabricator|Station|Refiner|Cistern|WindTrap|Windturbine|Silo|Extraction|Container|Pentashield|Generator|Collector|Vacuum/i.test(id) ? 'Stations & utilities'
  : /Light|Glow|Lamp/i.test(id) ? 'Lighting' : 'Furniture & decor');
const B_GROUPS = ['Structure sets', 'Stations & utilities', 'Furniture & decor', 'Lighting', 'Store & event bundles'];
async function renderBuilding(v) {
  if (!S.building) { S.building = await api('/api/building'); S.bPending = { sets: [...S.building.sets], pieces: [...S.building.pieces] }; }
  const P = S.bPending, cat = S.building.catalog, F = S.bFilter = S.bFilter || { q: '', show: 'all', group: 'all' };
  const dirty = JSON.stringify([...P.sets].sort()) !== JSON.stringify([...S.building.sets].sort()) || JSON.stringify(P.pieces) !== JSON.stringify(S.building.pieces);
  const have = new Set(P.sets), q = F.q.trim().toLowerCase();
  const all = Object.entries(cat.sets).map(([id, s]) => ({ id, ...s, group: bGroup(id) }));
  const shown = all.filter(s => (F.show === 'all' || (F.show === 'have') === have.has(s.id)) && (F.group === 'all' || s.group === F.group)
    && (!q || s.name.toLowerCase().includes(q) || s.id.toLowerCase().includes(q) || s.pieces.some(p => (cat.pieces[p] || p).toLowerCase().includes(q))));
  const unknown = P.sets.filter(x => !cat.sets[x]);
  const toggle = id => { if (have.has(id)) P.sets = P.sets.filter(x => x !== id); else P.sets.push(id); renderBuilding(v); };
  const bulk = on => { const ids = new Set(shown.map(s => s.id)); P.sets = on ? [...new Set([...P.sets, ...ids])] : P.sets.filter(x => !ids.has(x)); renderBuilding(v); };
  const chip = (label, active, fn) => h('button', { class: 'chip', 'aria-pressed': String(active), onclick: fn }, label);
  const search = h('input', { type: 'search', placeholder: 'Search sets or pieces…', value: F.q, style: 'flex:1;min-width:220px' });
  search.addEventListener('input', () => {
    F.q = search.value; clearTimeout(S.bT);
    S.bT = setTimeout(async () => { await renderBuilding(v); const i = v.querySelector('input[type=search]'); i.focus(); i.setSelectionRange(F.q.length, F.q.length); }, 250);
  });
  const card = s => ctile(have.has(s.id), `${s.name}\n${s.id}`, [h('div', { class: 'nm' }, s.name), h('div', { class: 'meta' }, `${s.pieces.length} pieces` + (s.desc ? ' \u00b7 ' + s.desc : '')),
    s.pieces.length ? h('details', {}, h('summary', { class: 'meta' }, 'Pieces'), h('div', { class: 'meta' }, s.pieces.map(p => cat.pieces[p] || p).join(' \u00b7 '))) : null], () => toggle(s.id));
  const setAll = (es, on) => { const ids = new Set(es.map(x => x.id)); P.sets = on ? [...new Set([...P.sets, ...ids])] : P.sets.filter(x => !ids.has(x)); renderBuilding(v); };
  const newPieces = h('details', { class: 'panel', style: 'margin-top:22px' }, h('summary', {}, `“New piece” markers in your save (${P.pieces.length}) — advanced`),
    h('p', { class: 'note' }, 'Pieces the game still flags as newly unlocked. Learning a set already gives you its pieces; you normally never need to touch this.'),
    h('div', { class: 'taglist' }, ...P.pieces.map(x => h('span', { class: 'tag' }, cat.pieces[x] || x,
      h('button', { title: 'Remove', onclick: () => { P.pieces = P.pieces.filter(y => y !== x); renderBuilding(v); } }, '×')))));
  v.replaceChildren(
    h('div', { class: 'stickybar' }, h('div', { class: 'row' },
      h('span', {}, dirty ? 'Building changes pending' : `${P.sets.length} of ${all.length} building sets learned`), h('span', { style: 'margin-left:auto' }),
      h('button', { class: 'btn', disabled: !dirty, onclick: () => { S.building = null; renderBuilding(v); } }, 'Revert'),
      h('button', { class: 'btn primary', disabled: !dirty, onclick: guard(async () => { await api('/api/building', P); S.building = null; await refreshState(); render(); toast('Staged. Use “Write to game” to save.'); }) }, 'Apply')),
      h('div', { class: 'row', style: 'margin-top:12px' }, search,
        h('button', { class: 'btn sm', onclick: () => bulk(true) }, `Learn all shown (${shown.length})`),
        h('button', { class: 'btn sm', onclick: () => bulk(false) }, 'Forget all shown')),
      h('div', { class: 'chips', style: 'margin-top:12px' },
        chip('All', F.show === 'all', () => { F.show = 'all'; renderBuilding(v); }), chip('Learned', F.show === 'have', () => { F.show = 'have'; renderBuilding(v); }),
        chip('Not learned', F.show === 'no', () => { F.show = 'no'; renderBuilding(v); }), h('span', { style: 'width:14px' }),
        chip('Any type', F.group === 'all', () => { F.group = 'all'; renderBuilding(v); }),
        ...B_GROUPS.map(g => chip(g, F.group === g, () => { F.group = g; renderBuilding(v); })))),
    aboutBox('Catalogue read from the game files: every building set (“patent”) with its pieces. Learning a set unlocks all its pieces in-game. Store & event bundles are cosmetic items normally sold or given as rewards.'),
    ...(unknown.length ? [h('div', { class: 'note', style: 'margin-top:10px' }, `Kept as-is (not in the catalogue): ${unknown.join(', ')}`)] : []),
    h('h2', { class: 'sect' }, `Building sets (${shown.length})`),
    ...(shown.length ? B_GROUPS.map(g => ({ g, es: shown.filter(x => x.group === g) })).filter(x => x.es.length)
      .map(x => groupBlock(x.g, x.es, y => have.has(y.id), setAll, card, ['Learn all', 'Forget all'])) : [h('div', { class: 'panel muted' }, 'No sets match.')]),
    newPieces);
}

/* ------------------------------------------------------------------ customisation (skins & swatches) */
const C_DOMAINS = [['armor', 'Armor & stillsuits'], ['weapon', 'Weapons'], ['vehicle', 'Vehicles'], ['placeable', 'Placeables'], ['other', 'Other']];
const hs = t => t.replace(/([a-z])([A-Z])/g, '$1 $2');
const slotLabel = e => e.tags.length ? e.tags[0].replace(/^Items\./, '').replace('Clothes.', '').replace('ScoutArmor', 'Light armor').replace('HeavyArmor', 'Heavy armor')
  .replace('Holsters.', '').replace('MeleeWeapons', 'Melee').replace('RangedWeapons', 'Ranged').replace(/\./g, ' › ') : e.folder.split('/').slice(0, 2).join(' › ');
async function renderCustom(v) {
  if (!S.cust) { S.cust = await api('/api/customization'); S.cPending = new Set(S.cust.owned); }
  const cat = S.cust.catalog, P = S.cPending, F = S.cFilter = S.cFilter || { q: '', kind: 'all', domain: 'armor', show: 'all' };
  const orig = new Set(S.cust.owned), q = F.q.trim().toLowerCase();
  const dirty = P.size !== orig.size || [...P].some(x => !orig.has(x));
  const known = new Set(cat.map(e => e.id)), unknown = [...P].filter(x => !known.has(x));
  const shown = cat.filter(e => (F.kind === 'all' || e.kind === F.kind) && (F.domain === 'all' || e.domain === F.domain)
    && (F.show === 'all' || (F.show === 'have') === P.has(e.id)) && (!q || e.name.toLowerCase().includes(q) || e.id.toLowerCase().includes(q) || slotLabel(e).toLowerCase().includes(q)));
  const inDomain = d => cat.filter(e => d === 'all' || e.domain === d);
  const toggle = id => { if (P.has(id)) P.delete(id); else P.add(id); renderCustom(v); };
  const bulk = on => { shown.forEach(e => (on ? P.add(e.id) : P.delete(e.id))); renderCustom(v); };
  const chip = (label, active, fn) => h('button', { class: 'chip', 'aria-pressed': String(active), onclick: fn }, label);
  const search = h('input', { type: 'search', placeholder: 'Search by name, id or slot…', value: F.q, style: 'flex:1;min-width:220px' });
  search.addEventListener('input', () => {
    F.q = search.value; clearTimeout(S.cT);
    S.cT = setTimeout(async () => { await renderCustom(v); const i = v.querySelector('input[type=search]'); i.focus(); i.setSelectionRange(F.q.length, F.q.length); }, 250);
  });
  const card = e => ctile(P.has(e.id), `${e.name}\n${e.id}${e.desc ? '\n' + e.desc : ''}`, [h('div', { class: 'nm' }, e.name),
    h('div', { class: 'meta' }, h('span', { class: 'kind ' + e.kind }, e.kind === 'skin' ? 'Skin' : 'Swatch'), ' \u00b7 ' + hs(slotLabel(e)))], () => toggle(e.id));
  const setAll = (es, on) => { es.forEach(e => (on ? P.add(e.id) : P.delete(e.id))); renderCustom(v); };
  const gname = e => hs(slotLabel(e).split(' \u203a ')[0]) || 'Other';
  const gnames = [...new Set(shown.map(gname))].sort();
  const owned = d => inDomain(d).filter(e => P.has(e.id)).length;
  v.replaceChildren(
    h('div', { class: 'stickybar' }, h('div', { class: 'row' },
      h('span', {}, dirty ? 'Customisation changes pending' : `${cat.filter(e => P.has(e.id)).length} of ${cat.length} skins & swatches unlocked`), h('span', { style: 'margin-left:auto' }),
      h('button', { class: 'btn', disabled: !dirty, onclick: () => { S.cust = null; renderCustom(v); } }, 'Revert'),
      h('button', { class: 'btn primary', disabled: !dirty, onclick: guard(async () => { await api('/api/customization', { owned: [...P] }); S.cust = null; await refreshState(); render(); toast('Staged. Use “Write to game” to save.'); }) }, 'Apply')),
      h('div', { class: 'row', style: 'margin-top:12px' }, search,
        h('button', { class: 'btn sm', onclick: () => bulk(true) }, `Unlock all shown (${shown.length})`), h('button', { class: 'btn sm', onclick: () => bulk(false) }, 'Lock all shown')),
      h('div', { class: 'chips', style: 'margin-top:12px' },
        ...C_DOMAINS.map(([d, l]) => chip(`${l} ${owned(d)}/${inDomain(d).length}`, F.domain === d, () => { F.domain = d; renderCustom(v); })), chip('Everything', F.domain === 'all', () => { F.domain = 'all'; renderCustom(v); })),
      h('div', { class: 'chips', style: 'margin-top:10px' },
        chip('Skins & swatches', F.kind === 'all', () => { F.kind = 'all'; renderCustom(v); }), chip('Skins only', F.kind === 'skin', () => { F.kind = 'skin'; renderCustom(v); }), chip('Swatches only', F.kind === 'swatch', () => { F.kind = 'swatch'; renderCustom(v); }),
        h('span', { style: 'width:14px' }),
        chip('All', F.show === 'all', () => { F.show = 'all'; renderCustom(v); }), chip('Unlocked', F.show === 'have', () => { F.show = 'have'; renderCustom(v); }), chip('Locked', F.show === 'no', () => { F.show = 'no'; renderCustom(v); }))),
    aboutBox('Catalogue read from the game files: every skin (mesh / material variant) and swatch (dye pack) for armor, stillsuits, weapons, vehicles and placeables. Unlocking adds the entry to your customisation library. Store & event items are normally sold or given as rewards.'),
    ...(unknown.length ? [h('div', { class: 'note', style: 'margin-top:10px' }, `Kept as-is (not in the catalogue): ${unknown.join(', ')}`)] : []),
    h('h2', { class: 'sect' }, `Skins & swatches (${shown.length})`),
    ...(shown.length ? gnames.map(g => groupBlock(g, shown.filter(e => gname(e) === g), e => P.has(e.id), setAll, card, ['Unlock all', 'Lock all'])) : [h('div', { class: 'panel muted' }, 'Nothing matches.')]));
}

/* ------------------------------------------------------------------ inventory */
const I_CATS = [['all', 'Everything'], ['resource', 'Resources'], ['ammo', 'Ammo'], ['weapon', 'Weapons'], ['tool', 'Tools'], ['armor', 'Armor & clothing'],
  ['equipment', 'Equipment'], ['consumable', 'Consumables'], ['augment', 'Augments'], ['schematic', 'Schematics'], ['cosmetic', 'Cosmetics'],
  ['vehicle', 'Vehicle parts'], ['placeable', 'Placeables'], ['building', 'Building'], ['emote', 'Emotes'], ['misc', 'Other']];
const I_ICON = {
  weapon: 'M5 19 19 5M14 5h5v5M7 17l-3 3', armor: 'M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z', ammo: 'M9 21V9a3 3 0 0 1 6 0v12zM9 15h6',
  resource: 'M12 3l7.5 4.5v9L12 21l-7.5-4.5v-9zM12 3v18M4.5 7.5 19.5 16.5', consumable: 'M12 3c4 5 6 8 6 11a6 6 0 0 1-12 0c0-3 2-6 6-11z',
  tool: 'M14 6a4 4 0 1 0 4 4l-9 9-3-3 9-9', equipment: 'M4 9h16v10H4zM9 9V5h6v4M4 14h16', schematic: 'M6 3h9l3 3v15H6zM9 11h6M9 15h6',
  augment: 'M12 3v5M12 16v5M3 12h5M16 12h5M9 12a3 3 0 1 0 6 0 3 3 0 1 0-6 0', cosmetic: 'M12 3l2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.2 6.4 20.2l1.1-6.2L3 9.6l6.2-.9z',
  vehicle: 'M3 15h18l-2-6H5zM3 15v3h18v-3M7 18v2M17 18v2', placeable: 'M4 20h16M6 20V9l6-5 6 5v11M10 20v-6h4v6', building: 'M4 20h16M6 20V9l6-5 6 5v11M10 20v-6h4v6',
  emote: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM8.5 14.5c2 2.5 5 2.5 7 0M9 10h.01M15 10h.01', contract: 'M6 3h9l3 3v15H6zM9 11h6M9 15h4', misc: 'M12 3l9 9-9 9-9-9z',
};
const iGlyph = c => { const s = h('span', { class: 'gl' }); s.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="${I_ICON[c] || I_ICON.misc}"/></svg>`; return s; };
const tierCol = t => (t >= 5 ? 'var(--g5)' : t >= 4 ? 'var(--g4)' : t >= 3 ? 'var(--g3)' : t >= 2 ? 'var(--g2)' : t >= 1 ? 'var(--g1)' : '#9a8d78');
const shortN = n => (n >= 1e6 ? (n / 1e6).toFixed(1).replace('.0', '') + 'M' : n >= 1e4 ? Math.round(n / 1e3) + 'k' : String(n));
const iHuman = id => id.replace(/^D_/, '').replace(/_/g, ' ').replace(/([a-z])([A-Z0-9])/g, '$1 $2');
const iInfo = (cat, tpl) => cat[tpl] || { n: iHuman(tpl), c: 'misc', m: 1, g: '', u: 1, unknown: 1 };
const iSub = e => [I_CATS.find(c => c[0] === e.c)?.[1] || 'Other', e.t ? 'Tier ' + e.t : '', e.r || '', e.off ? 'disabled in game' : ''].filter(Boolean).join(' · ');

async function renderInventory(v) {
  if (!S.inv) S.inv = await api('/api/inventory');
  const cat = S.inv.catalog, invs = S.inv.inventories, F = S.iFilter = S.iFilter || { inv: null, q: '', cat: 'all', sel: null, qty: 1, pick: null, mode: 'view', slot: null };
  if (!invs.some(i => i.id === F.inv)) F.inv = (invs.find(i => i.can_add) || invs[0]).id;
  const cur = invs.find(i => i.id === F.inv), backpack = invs.find(i => i.can_add);
  const picked = cur.items.find(i => i.id === F.pick) || null;
  if (!picked && F.mode === 'view') F.pick = null;
  const change = guard(async (ops, msg) => { await api('/api/inventory', { ops }); S.inv = null; await refreshState(); await render(); toast(msg || 'Staged. Use “Write to game” to save.'); });
  const again = () => renderInventory(v);

  /* ---- slot grid ---- */
  const cap = cur.max_items > 0 && cur.max_items <= 120 ? cur.max_items : 0;
  const bySlot = new Map(cur.items.map(i => [i.slot, i]));
  const tile = it => {
    const e = iInfo(cat, it.template);
    return h('button', { class: 'slot' + (it.id === F.pick ? ' sel' : ''), title: `${e.n}${it.qty > 1 ? ' × ' + fmt(it.qty) : ''}`, onclick: () => { F.pick = it.id; F.mode = 'view'; again(); } },
      h('span', { class: 'tdot', style: `background:${tierCol(e.t)}` }), it.qty > 1 ? h('span', { class: 'q' }, shortN(it.qty)) : null, iGlyph(e.c), h('span', { class: 'sn' }, e.n),
      it.durability != null && it.durability < 100 ? h('i', { class: 'dbar' }, h('b', { style: `width:${Math.max(3, it.durability)}%` })) : null);
  };
  const emptySlot = s => (cur.can_add ? h('button', { class: 'slot empty' + (F.mode === 'add' && F.slot === s ? ' sel' : ''), title: `Empty slot ${s + 1} — add an item`, 'aria-label': `Add item to slot ${s + 1}`,
    onclick: () => { F.mode = 'add'; F.slot = s; F.pick = null; again(); } }, h('span', { class: 'plus' }, '+')) : h('div', { class: 'slot empty' }));
  const cells = cap ? [...Array.from({ length: cap }, (_, s) => bySlot.get(s) ? tile(bySlot.get(s)) : emptySlot(s)), ...cur.items.filter(i => i.slot >= cap).map(tile)] : cur.items.map(tile);

  /* ---- side panel: selected item ---- */
  const detail = () => {
    if (!picked) return h('div', { class: 'panel side hintp' }, h('h3', { class: 'ph' }, 'Item details'),
      h('p', { class: 'muted' }, cur.can_add ? 'Select an item to change its amount or durability, or an empty slot to add something new.' : 'Select an item to change its amount or durability.'),
      cur.can_add ? h('button', { class: 'btn primary', onclick: () => { F.mode = 'add'; F.slot = null; again(); } }, 'Add item…') : null);
    const it = picked, e = iInfo(cat, it.template), top = e.unknown ? 10000000 : e.m, hasDur = it.durability != null || e.d;
    const setQ = n => { n = Math.max(1, Math.min(top, Math.round(Number(n)) || 1)); if (n !== it.qty) change([{ op: 'qty', id: it.id, qty: n }], `${e.n}: ${fmt(n)}`); else again(); };
    const qty = h('input', { type: 'number', min: 1, max: top, value: it.qty, disabled: top === 1 });
    qty.addEventListener('change', () => setQ(qty.value));
    const durNum = h('output', {}, hasDur ? Math.round(it.durability == null ? 100 : it.durability) + '%' : '');
    const dur = hasDur ? h('input', { type: 'range', min: 0, max: 100, step: 1, value: it.durability == null ? 100 : Math.round(it.durability) }) : null;
    if (dur) { dur.addEventListener('input', () => { durNum.textContent = dur.value + '%'; }); dur.addEventListener('change', () => change([{ op: 'durability', id: it.id, pct: Number(dur.value) }], `${e.n}: durability ${dur.value}%`)); }
    return h('div', { class: 'panel side' },
      h('div', { class: 'dhead' }, h('div', { class: 'dg' }, iGlyph(e.c)), h('div', {}, h('div', { class: 'dn' }, e.n), h('div', { class: 'note' }, `${iSub(e)} · slot ${it.slot + 1} of ${cur.label.toLowerCase()}`))),
      e.unknown ? h('div', { class: 'note warnbox' }, 'Not in the game-data catalogue, so its maximum stack is unknown.') : null,
      h('div', { class: 'dsec' }, h('div', { class: 'lab' }, 'Amount', top > 1 ? h('span', { class: 'muted' }, ` · stacks to ${fmt(top)}`) : h('span', { class: 'muted' }, ' · does not stack')),
        h('div', { class: 'stepper' }, h('button', { class: 'btn round', disabled: top === 1, 'aria-label': 'Decrease', onclick: () => setQ(it.qty - 1) }, '−'), qty,
          h('button', { class: 'btn round', disabled: top === 1, 'aria-label': 'Increase', onclick: () => setQ(it.qty + 1) }, '+')),
        top > 1 ? h('div', { class: 'chips', style: 'margin-top:10px' }, h('button', { class: 'chip', onclick: () => setQ(1) }, 'Min'), h('button', { class: 'chip', onclick: () => setQ(it.qty / 2) }, 'Half'),
          h('button', { class: 'chip', onclick: () => setQ(it.qty * 2) }, 'Double'), h('button', { class: 'chip', onclick: () => setQ(top) }, 'Full stack')) : null),
      hasDur ? h('div', { class: 'dsec' }, h('div', { class: 'lab' }, 'Durability ', durNum), dur, h('div', { class: 'chips', style: 'margin-top:10px' },
        h('button', { class: 'chip', onclick: () => change([{ op: 'durability', id: it.id, pct: 100 }], `${e.n} repaired`) }, 'Repair fully'))) : null,
      h('div', { class: 'dsec' }, h('code', {}, it.template)),
      h('div', { class: 'row', style: 'margin-top:14px' }, h('button', { class: 'btn danger', onclick: guard(async () => {
        if (await ask('Remove item?', h('p', {}, `Remove ${it.qty > 1 ? fmt(it.qty) + ' × ' : ''}${e.n} from your ${cur.label.toLowerCase()}?`), 'Remove')) { F.pick = null; await change([{ op: 'remove', id: it.id }], `${e.n} removed`); }
      }) }, 'Remove item')));
  };

  /* ---- side panel: add ---- */
  const q = F.q.trim().toLowerCase();
  const pool = Object.entries(cat).filter(([id, e]) => e.c !== 'contract' && (F.cat === 'all' || e.c === F.cat)
    && (!q || e.n.toLowerCase().includes(q) || id.toLowerCase().includes(q))).sort((a, b) => a[1].n.localeCompare(b[1].n));
  const adder = () => {
    const search = h('input', { type: 'search', placeholder: 'Search all items by name or id…', value: F.q, style: 'width:100%' });
    search.addEventListener('input', () => { F.q = search.value; clearTimeout(S.iT); S.iT = setTimeout(async () => { await again(); const i = v.querySelector('.side input[type=search]'); i.focus(); i.setSelectionRange(F.q.length, F.q.length); }, 250); });
    const sel = h('select', { style: 'width:100%' }, I_CATS.map(([k, l]) => h('option', { value: k, selected: F.cat === k }, l)));
    sel.addEventListener('change', () => { F.cat = sel.value; again(); });
    const chosen = F.sel && cat[F.sel] ? F.sel : null, ce = chosen && cat[chosen];
    const qtyIn = h('input', { type: 'number', min: 1, value: F.qty, style: 'width:110px' });
    qtyIn.addEventListener('input', () => { F.qty = Math.max(1, Math.round(Number(qtyIn.value)) || 1); });
    const free = backpack.max_items > 0 ? backpack.max_items - backpack.items.filter(i => i.slot < backpack.max_items).length : null;
    return h('div', { class: 'panel side' },
      h('div', { class: 'row' }, h('h3', { class: 'ph', style: 'margin:0' }, 'Add to backpack'), h('span', { style: 'margin-left:auto' }), h('button', { class: 'btn sm', onclick: () => { F.mode = 'view'; again(); } }, 'Close')),
      h('div', { class: 'note', style: 'margin:8px 0 12px' }, F.slot != null ? `Target: slot ${F.slot + 1}` : 'Target: first free slot', free != null ? ` · ${free} of ${backpack.max_items} slots free` : ''),
      search, h('div', { style: 'height:10px' }), sel,
      h('div', { class: 'pick' }, pool.length ? pool.slice(0, 80).map(([id, e]) => h('button', { class: 'pickrow' + (id === chosen ? ' sel' : ''), onclick: () => { F.sel = id; again(); } },
        h('span', { class: 'pn' }, iGlyph(e.c), h('span', {}, e.n)), h('span', { class: 'meta' }, (e.t ? 'T' + e.t : '') + (e.m > 1 ? ` ×${fmt(e.m)}` : '')))) : [h('div', { class: 'muted', style: 'padding:14px' }, 'No items match.')]),
      pool.length > 80 ? h('div', { class: 'note' }, `First 80 of ${fmt(pool.length)} matches — refine the search.`) : null,
      h('div', { class: 'dsec' }, ce ? h('div', {}, h('b', {}, ce.n), h('div', { class: 'note' }, iSub(ce) + (ce.m > 1 ? ` · stacks to ${fmt(ce.m)}, larger amounts use several slots` : ' · does not stack'))) : h('span', { class: 'muted' }, 'Pick an item from the list')),
      h('div', { class: 'row' }, h('label', { class: 'f' }, 'Quantity', qtyIn),
        h('button', { class: 'btn primary', style: 'align-self:flex-end', disabled: !ce, onclick: () => {
          const n = Math.max(1, Math.round(Number(qtyIn.value)) || 1); const slot = F.slot; F.mode = 'view'; F.slot = null;
          change([{ op: 'add', inv: backpack.id, template: chosen, qty: n, ...(slot != null ? { slot } : {}) }], `Added ${fmt(n)} × ${ce.n}`);
        } }, 'Add to backpack')));
  };

  v.replaceChildren(
    h('div', { class: 'invbar' }, h('div', { class: 'chips' }, ...invs.map(i => h('button', { class: 'chip', 'aria-pressed': String(i.id === F.inv), onclick: () => { F.inv = i.id; F.pick = null; F.mode = 'view'; F.slot = null; again(); } },
      `${i.label} ${i.items.length}${i.max_items > 0 ? '/' + i.max_items : ''}`))),
      h('details', { class: 'hint' }, h('summary', {}, 'About this tab'), h('p', {}, 'Changes are staged straight away; nothing touches your save until “Write to game” (which makes a backup first). Close the game before writing. Items are added to the backpack only; equip them in the game.'))),
    h('div', { class: 'invlayout' },
      h('div', {}, h('h2', { class: 'sect', style: 'margin-top:8px' }, `${cur.label} · ${cur.items.length}${cur.max_items > 0 ? ' of ' + cur.max_items : ''} slots used`),
        cells.length ? h('div', { class: 'slots' }, cells) : h('div', { class: 'panel muted' }, 'Empty.'),
        [1, 15, 30].includes(cur.type) ? h('p', { class: 'note', style: 'margin-top:14px' }, 'These items are equipped. You can change amounts and durability or remove them; to add gear, put it in the backpack and equip it in the game.') : null),
      F.mode === 'add' && backpack ? adder() : detail()));
}

/* ------------------------------------------------------------------ backups */
async function renderBackups(v) {
  const b = await api('/api/backups');
  v.replaceChildren(h('h2', { class: 'sect' }, 'Backups'),
    h('div', { class: 'row' }, h('button', { class: 'btn primary', disabled: !S.st.open, onclick: guard(async () => { const r = await api('/api/backup', { label: 'manual' }); toast('Backup created: ' + r.backup); renderBackups(v); }) }, 'Back up now'),
      h('span', { class: 'note' }, 'A full copy of the save folder is made automatically before every write.')),
    h('div', { style: 'height:10px' }),
    ...(b.backups.length ? b.backups.map(x => h('div', { class: 'save-card' },
      h('div', {}, h('div', {}, x.name), h('div', { class: 'muted' }, `${(x.bytes / 1024).toFixed(0)} KB · restores to ${x.origin}`)),
      h('button', { class: 'btn', disabled: !S.st.open, onclick: guard(async () => {
        if (!await ask('Restore this backup?', [h('p', {}, 'Your current save files are replaced with this backup (after making another backup first).'), h('p', { class: 'warn' }, 'Close Dune: Awakening first.')], 'Restore')) return;
        S.st = await api('/api/restore', { name: x.name }); S.skills = S.spec = S.recipes = S.building = S.cust = S.inv = null; renderChrome(); toast('Backup restored'); renderBackups(v);
      }) }, 'Restore')))
      : [h('div', { class: 'panel muted' }, 'No backups yet.')]));
}

/* ------------------------------------------------------------------ boot */
guard(async () => { await refreshState(); render(); })();
