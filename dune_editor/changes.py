"""Dashboard data: collection progress (summary) and the staged-vs-original comparison (snapshot / diff).
The original save is kept as a second SQLite file by savefile.Save, so a diff is just two snapshots."""
from __future__ import annotations

from . import editors
from .editors import load_json

_MAX_LINES = 40


def snapshot(conn):
    sk = editors.get_skills(conn)
    sp = editors.get_spec(conn)
    inv = {}
    for g in editors.get_inventory(conn):
        for it in g['items']:
            inv[it['id']] = {'inv': g['label'], 'template': it['template'], 'qty': it['qty'], 'dur': it['durability']}
    bld = editors.get_building(conn)
    return {
        'currency': {c['label']: c['balance'] for c in editors.get_currency(conn)},
        'tech': editors.get_tech_points(conn),
        'level': {'Total skill points': sk['total_points'], 'Unspent skill points': sk['unspent_points'], 'Total XP': sk['total_xp']},
        'ranks': {k: v for k, v in sk['ranks'].items() if v},
        'spec_levels': {t['name']: round(t['level']) for t in sp['tracks']},
        'keystones': {k['name'] for k in sp['keystones'] if k['owned']},
        'recipes': {r['id']: (r['grade'], r['count']) for r in editors.get_recipes(conn)},
        'sets': set(bld['sets']), 'pieces': set(bld['pieces']),
        'skins': set(editors.get_customization(conn)),
        'items': inv,
    }


def summary(conn):
    """Progress against the catalogues, for the dashboard tiles: [have, total]."""
    snap = snapshot(conn)
    cat = {'sets': load_json('building.json')['sets'], 'skins': {e['id'] for e in load_json('customization.json')},
           'recipes': {e['id'] for e in load_json('recipes.json')}, 'nodes': {n['tag'] for n in load_json('skills.json')['nodes']}}
    bp = next((g for g in editors.get_inventory(conn) if g['type'] == 0), None)
    return {
        'building': [len(snap['sets'] & set(cat['sets'])), len(cat['sets'])],
        'skins': [len(snap['skins'] & cat['skins']), len(cat['skins'])],
        'recipes': [len(set(snap['recipes']) & cat['recipes']), len(cat['recipes'])],
        'skills': [len(set(snap['ranks']) & cat['nodes']), len(cat['nodes'])],
        'spec': [sum(snap['spec_levels'].values()), 100 * len(snap['spec_levels'])],
        'backpack': [len([i for i in bp['items'] if i['slot'] < (bp['max_items'] or 10 ** 9)]), bp['max_items']] if bp else [0, 0],
        'items': len(snap['items']),
    }


def _names():
    items = load_json('items.json')
    skins = {e['id']: e['name'] for e in load_json('customization.json')}
    sets = {k: v['name'] for k, v in load_json('building.json')['sets'].items()}
    recipes = {e['id']: e['name'] for e in load_json('recipes.json')}
    nodes = {n['tag']: n['name'] for n in load_json('skills.json')['nodes']}
    return items, skins, sets, recipes, nodes


def _fmt(n):
    return f'{n:,}' if isinstance(n, int) else str(n)


def _set_lines(label, before, after, names):
    add, rem = sorted(after - before), sorted(before - after)
    out = []
    if add:
        out.append(f'+ {len(add)} {label}: ' + ', '.join(names.get(a, a) for a in add[:6]) + (f' and {len(add) - 6} more' if len(add) > 6 else ''))
    if rem:
        out.append(f'− {len(rem)} {label}: ' + ', '.join(names.get(a, a) for a in rem[:6]) + (f' and {len(rem) - 6} more' if len(rem) > 6 else ''))
    return out


def diff(base, cur):
    items, skins, sets, recipes, nodes = _names()
    groups = []

    def group(area, lines):
        if lines:
            groups.append({'area': area, 'lines': lines[:_MAX_LINES], 'more': max(0, len(lines) - _MAX_LINES)})

    group('Wallet', [f'{k}: {_fmt(base["currency"][k])} → {_fmt(cur["currency"][k])}' for k in cur['currency'] if base['currency'].get(k) != cur['currency'][k]]
          + ([f'Tech knowledge points: {_fmt(base["tech"])} → {_fmt(cur["tech"])}'] if base['tech'] != cur['tech'] else []))
    group('Level', [f'{k}: {_fmt(base["level"][k])} → {_fmt(cur["level"][k])}' for k in cur['level'] if base['level'][k] != cur['level'][k]])
    lines = []
    for tag in sorted(set(base['ranks']) | set(cur['ranks'])):
        if base['ranks'].get(tag, 0) != cur['ranks'].get(tag, 0):
            lines.append(f'{nodes.get(tag, tag)}: rank {base["ranks"].get(tag, 0)} → {cur["ranks"].get(tag, 0)}')
    group('Skills', lines)
    lines = [f'{k} level {base["spec_levels"].get(k, 0)} → {v}' for k, v in cur['spec_levels'].items() if base['spec_levels'].get(k) != v]
    group('Specializations', lines + _set_lines('traits', base['keystones'], cur['keystones'], {}))
    lines = _set_lines('recipes', set(base['recipes']), set(cur['recipes']), recipes)
    for rid in sorted(set(base['recipes']) & set(cur['recipes'])):
        if base['recipes'][rid] != cur['recipes'][rid]:
            (g0, c0), (g1, c1) = base['recipes'][rid], cur['recipes'][rid]
            lines.append(f'{recipes.get(rid, rid)}: grade {g0} × {c0} → grade {g1} × {c1}')
    group('Recipes', lines)
    group('Building sets', _set_lines('sets', base['sets'], cur['sets'], sets))
    group('Skins & swatches', _set_lines('items', base['skins'], cur['skins'], skins))
    lines = []
    for iid, it in cur['items'].items():
        nm = items.get(it['template'], {}).get('n', it['template'])
        if iid not in base['items']:
            lines.append(f'+ {nm} × {_fmt(it["qty"])}  ({it["inv"]})')
            continue
        b = base['items'][iid]
        if b['qty'] != it['qty']:
            lines.append(f'{nm}: {_fmt(b["qty"])} → {_fmt(it["qty"])}  ({it["inv"]})')
        if b['dur'] != it['dur']:
            f = lambda d: 'full' if d is None else f'{round(d)}%'
            lines.append(f'{nm}: durability {f(b["dur"])} → {f(it["dur"])}')
    for iid, b in base['items'].items():
        if iid not in cur['items']:
            lines.append(f'− {items.get(b["template"], {}).get("n", b["template"])} × {_fmt(b["qty"])}  ({b["inv"]})')
    group('Inventory', lines)
    return groups
