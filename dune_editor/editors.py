"""Read/modify the parts of a Dune: Awakening save. Every function takes the open sqlite connection."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import fmt
from .fmt import Node, LongKey

DATA = Path(__file__).resolve().parent.parent / 'data'

# currency_id -> label (confirmed against the in-game header, which shows Solari and House Script)
CURRENCIES = {0: 'Solari', 1: 'House Script'}
# track_type -> specialization track. 1 is confirmed (Crafting); 2-5 follow the in-game row order.
TRACKS = {1: 'Crafting', 2: 'Gathering', 3: 'Exploration', 4: 'Combat', 5: 'Sabotage'}
TRACKS_CONFIRMED = {1}
MAX_SPEC_LEVEL = 100


class EditError(Exception):
    pass


def load_json(name):
    return json.loads((DATA / name).read_text(encoding='utf-8'))


# ======================================================================
# identity
# ======================================================================
def ids(conn):
    row = conn.execute('select id, account_id, character_name, player_controller_id, player_pawn_id '
                       'from player_state order by id limit 1').fetchone()
    if not row:
        raise EditError('no player character found in this save')
    acc = conn.execute('select funcom_id, platform_id from accounts where id=?', (row[1],)).fetchone()
    return {'state_id': row[0], 'account_id': row[1], 'name': row[2], 'controller': row[3], 'pawn': row[4],
            'funcom_id': (acc[0] if acc else '').replace('%23', '#').replace('%20', ' '),
            'platform_id': acc[1] if acc else ''}


def _load_blob(conn, sql, args):
    row = conn.execute(sql, args).fetchone()
    if not row or row[0] is None:
        raise EditError('expected save data is missing')
    return fmt.decode(row[0])


def pawn_props(conn):
    return _load_blob(conn, 'select properties from actors where id=?', (ids(conn)['pawn'],))


def save_pawn_props(conn, node):
    conn.execute('update actors set properties=? where id=?', (fmt.encode(node), ids(conn)['pawn']))


def _entity_id(conn):
    row = conn.execute("select entity_id from actor_fgl_entities where actor_id=? and slot_name='DuneCharacter'",
                       (ids(conn)['pawn'],)).fetchone()
    if not row:
        raise EditError('character entity not found')
    return row[0]


def char_entity(conn):
    return _load_blob(conn, 'select components from fgl_entities where entity_id=?', (_entity_id(conn),))


def save_char_entity(conn, node):
    conn.execute('update fgl_entities set components=? where entity_id=?', (fmt.encode(node), _entity_id(conn)))


def _int(node):
    return int(node.value)


# ======================================================================
# currency
# ======================================================================
def get_currency(conn):
    c = ids(conn)['controller']
    have = {r[0]: r[1] for r in conn.execute('select currency_id, balance from player_virtual_currency_balances '
                                              'where player_controller_id=?', (c,))}
    return [{'id': k, 'label': v, 'balance': have.get(k, 0)} for k, v in CURRENCIES.items()]


def set_currency(conn, balances: dict):
    c = ids(conn)['controller']
    for cid, bal in balances.items():
        cid, bal = int(cid), int(bal)
        if cid not in CURRENCIES:
            raise EditError(f'unknown currency {cid}')
        if not 0 <= bal <= 2_000_000_000:
            raise EditError('balance must be between 0 and 2,000,000,000')
        cur = conn.execute('update player_virtual_currency_balances set balance=? where player_controller_id=? and currency_id=?',
                           (bal, c, cid))
        if cur.rowcount == 0:
            conn.execute('insert into player_virtual_currency_balances(player_controller_id, currency_id, balance) values (?,?,?)',
                         (c, cid, bal))


# ======================================================================
# class skills (FLevelComponent)
# ======================================================================
_TAG = re.compile(r'"([^"\\]+)')


def _level_struct(root):
    lc = root.get('FLevelComponent')
    if lc is None or lc.kind != 'A' or len(lc.value) < 2 or lc.value[1].kind != 'S':
        raise EditError('skill data (FLevelComponent) not found or in an unexpected shape')
    return lc.value[1]


def _module_data(st):
    md = st.get('ModuleData')
    if md is None or md.kind != 'S':
        raise EditError('ModuleData missing')
    return md


def get_skills(conn):
    st = _level_struct(char_entity(conn))
    ranks = {}
    for k, v in _module_data(st).value:
        m = _TAG.search(k)
        sp = v.get('SkillPointsSpent')
        if m and sp is not None:
            ranks[m.group(1)] = _int(sp)
    g = lambda key: _int(st.get(key)) if st.get(key) is not None else 0
    active = [n.get('TagName').value for n in (st.get('ActiveAbilityTags').value if st.get('ActiveAbilityTags') else [])]
    return {'ranks': ranks, 'total_points': g('TotalSkillPoints'), 'unspent_points': g('UnspentSkillPoints'),
            'bonus_points': g('KeystoneBonusSkillPoints'), 'total_xp': g('TotalXPEarned'),
            'level': g('TotalSkillPoints') + 1, 'active_abilities': active}


def set_skills(conn, ranks: dict | None = None, total_points=None, unspent_points=None, total_xp=None):
    cat = {n['tag']: n for n in load_json('skills.json')['nodes']}
    root = char_entity(conn)
    st = _level_struct(root)
    md = _module_data(st)
    index = {}
    for i, (k, v) in enumerate(md.value):
        m = _TAG.search(k)
        if m:
            index[m.group(1)] = v
    for tag, rank in (ranks or {}).items():
        rank = int(rank)
        mx = cat.get(tag, {}).get('max', 3)
        if not 0 <= rank <= mx:
            raise EditError(f'{tag}: rank must be 0..{mx}')
        node = index.get(tag)
        if node is None:
            node = Node('S', [('SkillPointsSpent', Node('i', '0'))])
            md.value.append((LongKey('(TagName=\\"' + tag + '\\")'), node))
            index[tag] = node
        node.get('SkillPointsSpent').value = str(rank)
    for key, val, hi in (('TotalSkillPoints', total_points, 5000), ('UnspentSkillPoints', unspent_points, 5000),
                         ('TotalXPEarned', total_xp, 2_000_000_000)):
        if val is None:
            continue
        val = int(val)
        if not 0 <= val <= hi:
            raise EditError(f'{key} must be between 0 and {hi}')
        st.get(key).value = str(val)
    save_char_entity(conn, root)


# ======================================================================
# specializations
# ======================================================================
_KS = re.compile(r'^(Combat|Crafting|Exploration|Gathering|Sabotage)_\w*?Keystone_(.+?)(\d*)$')   # trait name + unlock level (a few have none)


def xp_curve():
    return load_json('xp_curve.json')


def level_to_xp(level: float):
    c = xp_curve()
    whole = max(0, min(MAX_SPEC_LEVEL, int(level)))
    if whole >= MAX_SPEC_LEVEL:
        return c[MAX_SPEC_LEVEL]
    frac = float(level) - whole
    return int(round(c[whole] + frac * (c[whole + 1] - c[whole])))


def get_spec(conn):
    ctl = ids(conn)['controller']
    tracks = [{'track': t, 'name': TRACKS.get(t, f'Track {t}'), 'confirmed': t in TRACKS_CONFIRMED, 'xp': xp, 'level': lvl}
              for t, xp, lvl in conn.execute('select track_type, xp_amount, level from specialization_tracks '
                                              'where player_id=? order by track_type', (ctl,))]
    bought = {r[0] for r in conn.execute('select k.name from purchased_specialization_keystones p '
                                          'join specialization_keystones_map k on k.id=p.keystone_id where p.player_id=?', (ctl,))}
    keys = []
    for (name,) in conn.execute('select name from specialization_keystones_map order by id'):
        m = _KS.match(name)
        if not m:
            continue
        keys.append({'name': name, 'track': m.group(1), 'base': m.group(2), 'level': int(m.group(3) or 0), 'owned': name in bought})
    return {'tracks': tracks, 'keystones': keys, 'max_level': MAX_SPEC_LEVEL, 'curve': xp_curve()}


def set_spec(conn, levels: dict | None = None, keystones: list | None = None):
    ctl = ids(conn)['controller']
    for t, lvl in (levels or {}).items():
        t, lvl = int(t), float(lvl)
        if not 0 <= lvl <= MAX_SPEC_LEVEL:
            raise EditError(f'level must be 0..{MAX_SPEC_LEVEL}')
        xp = level_to_xp(lvl)
        cur = conn.execute('update specialization_tracks set xp_amount=?, level=? where player_id=? and track_type=?', (xp, lvl, ctl, t))
        if cur.rowcount == 0:
            conn.execute('insert into specialization_tracks(player_id, track_type, xp_amount, level) values (?,?,?,?)', (ctl, t, xp, lvl))
    if keystones is not None:
        want = set(keystones)
        ids_by_name = {n: i for i, n in conn.execute('select id, name from specialization_keystones_map')}
        unknown = [n for n in want if n not in ids_by_name]
        if unknown:
            raise EditError('unknown keystones: ' + ', '.join(unknown[:5]))
        conn.execute('delete from purchased_specialization_keystones where player_id=?', (ctl,))
        conn.executemany('insert into purchased_specialization_keystones(player_id, keystone_id) values (?,?)',
                         [(ctl, ids_by_name[n]) for n in sorted(want)])


# ======================================================================
# known crafting recipes
# ======================================================================
def _recipe_array(root):
    comp = root.get('CraftingRecipesLibraryActorComponent')
    arr = comp.get('m_KnownItemRecipes') if comp is not None else None
    if arr is None or arr.kind != 'A':
        raise EditError('known recipe list not found in the expected place')
    return arr


def _entry_info(e):
    try:
        return {'id': e.get('BaseRecipeId').get('Name').value, 'grade': _int(e.get('m_QualityLevel')),
                'count': _int(e.get('m_NumberOfRecipeUses')) if e.get('m_NumberOfRecipeUses') else None,
                'limited': e.get('m_bIsLimitedUseRecipe').value == 1 if e.get('m_bIsLimitedUseRecipe') else False}
    except AttributeError:
        return None


def get_recipes(conn):
    out = []
    for e in _recipe_array(pawn_props(conn)).value:
        info = _entry_info(e)
        if info:
            out.append(info)
    return out


def _new_entry(rid, grade, count):
    return Node('S', [('BaseRecipeId', Node('S', [('Name', Node('s', rid))])),
                      ('m_QualityLevel', Node('i', str(grade))),
                      ('m_bIsNew', Node('b', 1)),
                      ('m_NumberOfRecipeUses', Node('i', str(count))),
                      ('m_bIsLimitedUseRecipe', Node('b', 1)),
                      ('m_Source', Node('s', 'SchematicPickup'))])


def set_recipes(conn, items: list):
    """items: [{id, grade, count}] -> set the known count of each recipe at that grade (adds it if missing)."""
    valid = {r['id'] for r in load_json('recipes.json')}
    root = pawn_props(conn)
    arr = _recipe_array(root)
    index = {}
    for e in arr.value:
        info = _entry_info(e)
        if info:
            index[(info['id'].lower(), info['grade'])] = e
    added = changed = 0
    for it in items:
        rid, grade, count = it['id'], int(it['grade']), int(it['count'])
        if rid not in valid:
            raise EditError(f'unknown recipe id: {rid}')
        if not 0 <= grade <= 5 or not 1 <= count <= 99:
            raise EditError(f'{rid}: grade must be 0..5 and count 1..99')
        e = index.get((rid.lower(), grade))
        if e is None:
            e = _new_entry(rid, grade, count)
            arr.value.append(e)
            index[(rid.lower(), grade)] = e
            added += 1
        else:
            if e.get('m_bIsLimitedUseRecipe') is None or e.get('m_bIsLimitedUseRecipe').value != 1 or e.get('m_NumberOfRecipeUses') is None:
                raise EditError(f'{rid} grade {grade} is a permanent recipe; its count cannot be changed')
            if _int(e.get('m_NumberOfRecipeUses')) != count:
                changed += 1
            e.get('m_NumberOfRecipeUses').value = str(count)
    save_pawn_props(conn, root)
    return {'added': added, 'changed': changed}


# ======================================================================
# customisations: armor / weapon / vehicle skins (mesh variants) and swatches (dye packs)
# ======================================================================
def _custom_array(root):
    comp = root.get('CustomizationLibraryActorComponent')
    lst = comp.get('m_UnlockedCustomizationSerializableList') if comp is not None else None
    arr = lst.get('m_UnlockedCustomizationIds') if lst is not None else None
    if arr is None or arr.kind != 'A':
        raise EditError('unlocked customisation list not found in the expected place')
    return arr


def get_customization(conn):
    return [e.get('m_CustomizationId').value for e in _custom_array(pawn_props(conn)).value if e.get('m_CustomizationId') is not None]


def set_customization(conn, wanted: list):
    """wanted: the complete list of customisation ids the character should own (existing entries keep their order)."""
    name = re.compile(r'^[A-Za-z0-9_\- ]{2,120}$')
    bad = [w for w in wanted if not isinstance(w, str) or not name.match(w)]
    if bad:
        raise EditError('invalid customisation ids: ' + ', '.join(map(str, bad[:3])))
    root = pawn_props(conn)
    arr = _custom_array(root)
    want = set(wanted)
    kept = [e for e in arr.value if e.get('m_CustomizationId') is not None and e.get('m_CustomizationId').value in want]
    have = {e.get('m_CustomizationId').value for e in kept}
    added = [w for w in dict.fromkeys(wanted) if w not in have]
    removed = len(arr.value) - len(kept)
    arr.value = kept + [Node('S', [('m_CustomizationId', Node('s', w))]) for w in added]
    save_pawn_props(conn, root)
    return {'added': len(added), 'removed': removed, 'total': len(arr.value)}


# ======================================================================
# building recipes (patents) and tech points
# ======================================================================
def get_building(conn):
    cid = ids(conn)['state_id']
    return {'sets': [r[0] for r in conn.execute('select learned_building_set from building_progression_learned_building_sets '
                                                 'where character_id=? order by 1', (cid,))],
            'pieces': [r[0] for r in conn.execute('select new_buildable_piece from building_progression_new_buildable_pieces '
                                                   'where character_id=? order by 1', (cid,))]}


def set_building(conn, sets=None, pieces=None):
    cid = ids(conn)['state_id']
    name = re.compile(r'^[A-Za-z0-9_\-]{2,120}$')
    for table, col, vals in (('building_progression_learned_building_sets', 'learned_building_set', sets),
                              ('building_progression_new_buildable_pieces', 'new_buildable_piece', pieces)):
        if vals is None:
            continue
        bad = [v for v in vals if not name.match(v)]
        if bad:
            raise EditError('invalid names: ' + ', '.join(bad[:3]))
        conn.execute(f'delete from {table} where character_id=?', (cid,))
        conn.executemany(f'insert into {table}(character_id, {col}) values (?,?)', [(cid, v) for v in sorted(set(vals))])


def get_tech_points(conn):
    hits = list(fmt.find_all(pawn_props(conn), 'm_TechKnowledgePoints'))
    return _int(hits[0][1]) if hits else None


def set_tech_points(conn, value):
    value = int(value)
    if not 0 <= value <= 1_000_000:
        raise EditError('tech points must be 0..1,000,000')
    root = pawn_props(conn)
    hits = list(fmt.find_all(root, 'm_TechKnowledgePoints'))
    if not hits:
        raise EditError('tech points not found in this save')
    hits[0][1].value = str(value)
    save_pawn_props(conn, root)


# ======================================================================
# inventory: the character's item containers (backpack, worn gear, hand-held tools, ...)
# ======================================================================
# inventory_type -> label. 0/1/15/29 are identified from their contents; 30 holds consumable/tool gear (name is a guess).
INV_LABELS = {0: 'Backpack', 1: 'Worn gear', 15: 'Hand-held (weapons & tools)', 30: 'Quick-use gear', 29: 'Contract items',
              14: 'Owned emotes', 27: 'Emote wheel'}
INV_ADD_TYPES = (0,)              # new items are only placed in the backpack; equipping them is left to the game
_TEMPLATE = re.compile(r'^[A-Za-z0-9_\-]{2,120}$')
_MAX_NEW_STACKS = 200


def _inv_stats(text):
    try:
        return json.loads(text)
    except ValueError:
        return {}


def _durability(stats):
    d = stats.get('FItemStackAndDurabilityStats')
    if isinstance(d, list) and len(d) == 2 and isinstance(d[1], dict):
        return d[1].get('CurrentDurability')
    return None


def get_inventory(conn):
    pawn = ids(conn)['pawn']
    out = []
    for iid, typ, maxn, maxv in conn.execute('select id, inventory_type, max_item_count, max_item_volume from inventories '
                                             'where actor_id=? and inventory_type is not null order by inventory_type', (pawn,)).fetchall():
        rows = conn.execute('select id, stack_size, position_index, template_id, is_new, stats from items '
                            'where inventory_id=? order by position_index, id', (iid,)).fetchall()
        if not rows and typ not in INV_ADD_TYPES:
            continue
        items = []
        for r in rows:
            st = _inv_stats(r[5])
            items.append({'id': r[0], 'qty': r[1], 'slot': r[2], 'template': r[3], 'new': bool(r[4]),
                          'durability': _durability(st), 'stat_kinds': sorted(k for k in st if k != 'FItemStackAndDurabilityStats')})
        out.append({'id': iid, 'type': typ, 'label': INV_LABELS.get(typ, f'Inventory type {typ}'), 'max_items': maxn,
                    'max_volume': maxv, 'can_add': typ in INV_ADD_TYPES, 'items': items})
    return out


def _fresh_stats(conn, template, cat, catalog):
    """Stats JSON for a new item: the same set of stat structs as an item of this kind already in the save (all values
    reset to their defaults), because the game expects e.g. weapon / clothing / fillable structs to exist."""
    best, score = None, -1
    grp = (cat or {}).get('g', '').split('.')
    for tid, st in conn.execute('select template_id, stats from items').fetchall():
        if tid == template:
            best, score = st, 99
            break
        e = catalog.get(tid)
        if not e or not cat or e['c'] != cat['c'] or e['c'] == 'contract':
            continue
        g = e.get('g', '').split('.')
        sc = 0
        while sc < min(len(g), len(grp)) and g[sc] == grp[sc]:
            sc += 1
        if sc > score:
            best, score = st, sc
    if best is None:
        return '{"FItemStackAndDurabilityStats":[[],{}]}'
    keys = [k for k in _inv_stats(best) if not k.startswith('FContract')]
    if 'FItemStackAndDurabilityStats' not in keys:
        keys.insert(0, 'FItemStackAndDurabilityStats')
    return json.dumps({k: [[], {}] for k in keys}, separators=(',', ':'))


def _whole(v, lo, hi, what):
    if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
        raise EditError(f'{what} must be a whole number from {lo:,} to {hi:,}')
    return v


def apply_inventory(conn, ops: list):
    """ops: [{'op':'qty','id':item,'qty':n} | {'op':'durability','id':item,'pct':0..100} | {'op':'remove','id':item} |
    {'op':'add','template':id,'qty':n,'inv':inventory id}] - all or nothing."""
    if not isinstance(ops, list) or not ops:
        raise EditError('nothing to change')
    catalog = load_json('items.json')
    pawn = ids(conn)['pawn']
    mine = {r[0]: r for r in conn.execute('select id, inventory_type, max_item_count from inventories where actor_id=?', (pawn,))}
    res = {'qty': 0, 'durability': 0, 'removed': 0, 'added': 0}
    conn.execute('savepoint inv')
    try:
        for op in ops:
            kind = op.get('op')
            if kind in ('qty', 'durability', 'remove'):
                row = conn.execute('select id, inventory_id, stats, template_id from items where id=?', (op.get('id'),)).fetchone()
                if not row or row[1] not in mine:
                    raise EditError("that item is not in your character's inventory")
                if kind == 'remove':
                    conn.execute('delete from items where id=?', (row[0],))
                    res['removed'] += 1
                elif kind == 'qty':
                    top = catalog[row[3]]['m'] if row[3] in catalog else 10_000_000
                    conn.execute('update items set stack_size=? where id=?', (_whole(op.get('qty'), 1, top, 'quantity'), row[0]))
                    res['qty'] += 1
                else:
                    pct = op.get('pct')
                    if not isinstance(pct, (int, float)) or isinstance(pct, bool) or not 0 <= pct <= 100:
                        raise EditError('durability must be 0..100')
                    st = _inv_stats(row[2])
                    base = st.get('FItemStackAndDurabilityStats')
                    if not (isinstance(base, list) and len(base) == 2 and isinstance(base[1], dict)):
                        raise EditError('this item has no durability')
                    if pct >= 100:
                        base[1].pop('CurrentDurability', None)
                    else:
                        base[1]['CurrentDurability'] = float(pct)
                    conn.execute('update items set stats=? where id=?', (json.dumps(st, separators=(',', ':')), row[0]))
                    res['durability'] += 1
            elif kind == 'add':
                inv, tpl = op.get('inv'), op.get('template')
                if inv not in mine or mine[inv][1] not in INV_ADD_TYPES:
                    raise EditError('new items can only be added to the backpack')
                if not isinstance(tpl, str) or not _TEMPLATE.match(tpl):
                    raise EditError('invalid item id')
                cat = catalog.get(tpl)
                if cat is None and not conn.execute('select 1 from items where template_id=? limit 1', (tpl,)).fetchone():
                    raise EditError(f'unknown item: {tpl}')
                q = _whole(op.get('qty'), 1, 10_000_000, 'quantity')
                per = cat['m'] if cat else conn.execute('select max(stack_size) from items where template_id=?', (tpl,)).fetchone()[0]
                stacks = []
                while q > 0:
                    stacks.append(min(per, q))
                    q -= stacks[-1]
                if len(stacks) > _MAX_NEW_STACKS:
                    raise EditError(f'that would need {len(stacks)} stacks; add fewer at once')
                used = {r[0] for r in conn.execute('select position_index from items where inventory_id=?', (inv,))}
                cap = mine[inv][2]
                slots, p, want = [], 0, op.get('slot')       # optional preferred slot for the first stack
                if isinstance(want, int) and not isinstance(want, bool) and 0 <= want < (cap if cap and cap > 0 else 10 ** 6) and want not in used:
                    slots.append(want)
                while len(slots) < len(stacks):
                    if cap and cap > 0 and p >= cap:
                        raise EditError(f'the backpack is full ({cap} slots); free some slots first')
                    if p not in used and p not in slots:
                        slots.append(p)
                    p += 1
                stats = _fresh_stats(conn, tpl, cat, catalog)
                nxt = conn.execute('select next_id from items_id_sequencer').fetchone()[0]
                now = int(time.time())
                for sz, pos in zip(stacks, slots):
                    conn.execute('insert into items(id, inventory_id, stack_size, position_index, template_id, is_new, '
                                 'acquisition_time, stats, quality_level) values (?,?,?,?,?,1,?,?,0)',
                                 (nxt, inv, sz, pos, tpl, now, stats))
                    nxt += 1
                conn.execute('update items_id_sequencer set next_id=?', (nxt,))
                res['added'] += len(stacks)
            else:
                raise EditError('unknown inventory change')
    except Exception:
        conn.execute('rollback to inv')
        raise
    finally:
        conn.execute('release inv')
    return res


# ======================================================================
# overview
# ======================================================================
def overview(conn):
    me = ids(conn)
    sk = get_skills(conn)
    return {'name': me['name'], 'funcom_id': me['funcom_id'], 'platform_id': me['platform_id'],
            'currency': get_currency(conn), 'level': sk['level'], 'total_points': sk['total_points'],
            'unspent_points': sk['unspent_points'], 'tech_points': get_tech_points(conn)}
