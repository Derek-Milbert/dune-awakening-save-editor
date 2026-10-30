"""Build data/items.json (every inventory item template in the game) from the game's DT_BaseItems_* data tables and
ST_Localization_Items, extracted with retoc:
    retoc to-legacy --no-shaders -f Systems/Items/BaseItems <Paks> <out dir>
usage: python tools/build_item_data.py <dir containing DT_BaseItems_*.uasset> [items_st.json]
items_st.json is a {key: text} dump of ST_Localization_Items (see build_customization_data.py for the reader).

Each table is a UE DataTable with tagged properties, so rows are walked with the property sizes: row FName, then
(name FName, type FName, size, array index, type-specific tag, guid flag, value) until the FName 'None'."""
import json, os, re, struct, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Bad(Exception):
    pass


def read_names(a):
    """name map of a legacy .uasset: found by scanning the summary for a plausible (NameCount, NameOffset) pair."""
    for off in range(0x20, 0x400):
        cnt, o = struct.unpack_from('<ii', a, off)
        if not (10 < cnt < 200000 and 0x40 < o < len(a)): continue
        p, out = o, []
        try:
            for _ in range(cnt):
                n = struct.unpack_from('<i', a, p)[0]
                if n > 0: out.append(a[p + 4:p + 3 + n].decode()); p += 4 + n
                else: out.append(a[p + 4:p + 2 - 2 * n].decode('utf-16le')); p += 4 - 2 * n
                p += 4
            return out
        except (struct.error, UnicodeDecodeError): continue
    raise SystemExit('name table not found')


def fname(x, p, n):
    i, k = struct.unpack_from('<ii', x, p)
    if not (0 <= i < len(n)) or not (0 <= k < 1000): raise Bad(p)
    return n[i]


def read_props(x, p, n, end=None):
    """tagged properties up to 'None' -> (props{name: (type, size, value offset, extra)}, offset after 'None')."""
    props = {}
    while end is None or p < end:
        pn = fname(x, p, n); p += 8
        if pn == 'None': break
        pt = fname(x, p, n); p += 8
        size = struct.unpack_from('<i', x, p)[0]; p += 8
        extra = None
        if pt == 'StructProperty': extra = fname(x, p, n); p += 8 + 16
        elif pt == 'BoolProperty': extra = x[p]; p += 1
        elif pt in ('ByteProperty', 'EnumProperty', 'ArrayProperty', 'SetProperty'): extra = fname(x, p, n); p += 8
        elif pt == 'MapProperty': extra = (fname(x, p, n), fname(x, p + 8, n)); p += 16
        if x[p]: p += 16
        p += 1
        if size < 0 or p + size > len(x): raise Bad(p)
        props[pn] = (pt, size, p, extra)
        if pt != 'BoolProperty': p += size
    return props, p


def read_table(a, x):
    n = read_names(a)
    for k in range(400):
        cnt = struct.unpack_from('<i', x, k)[0]
        if not 0 < cnt < 20000: continue
        try:
            p, rows = k + 4, {}
            for _ in range(cnt):
                rn = fname(x, p, n)
                rows[rn], p = read_props(x, p + 8, n)
            return n, rows
        except (Bad, struct.error): continue
    raise SystemExit('data table rows not found')


def fstring(x, p):
    """-> (text, offset after it)"""
    ln = struct.unpack_from('<i', x, p)[0]
    if ln > 0: return x[p + 4:p + 3 + ln].decode('utf-8', 'replace'), p + 4 + ln
    if ln < 0: return x[p + 4:p + 2 - 2 * ln].decode('utf-16le', 'replace'), p + 4 - 2 * ln
    return '', p + 4


def text_key(x, o):
    ht = struct.unpack_from('<b', x, o + 4)[0]
    if ht == 0:                                              # base text: namespace, key, source string
        return fstring(x, fstring(x, o + 5)[1])[0]
    if ht == 11: return fstring(x, o + 5 + 8)[0]             # string table reference: table id FName, key
    return None


def row_info(x, n, props):
    r = {}
    sd = props.get('StaticData')
    if sd:
        sp, _ = read_props(x, sd[2], n, sd[2] + sd[1])
        for k, (t, s, o, e) in sp.items():
            if t == 'TextProperty' and k in ('Name', 'ShortDesc'): r[k] = text_key(x, o)
            elif t == 'IntProperty': r[k] = struct.unpack_from('<i', x, o)[0]
            elif t == 'FloatProperty': r[k] = struct.unpack_from('<f', x, o)[0]
            elif t == 'BoolProperty': r[k] = e
            elif k == 'ItemTags':
                c = struct.unpack_from('<i', x, o)[0]
                r['tags'] = [fname(x, o + 4 + 8 * i, n) for i in range(c)]
    sdur = props.get('StackAndDurability')
    if sdur:
        sp, _ = read_props(x, sdur[2], n, sdur[2] + sdur[1])
        for k in ('MaxStackSize', 'MaxDurability'):
            if k in sp: r[k] = struct.unpack_from('<i' if sp[k][0] == 'IntProperty' else '<f', x, sp[k][2])[0]
    r['dep'] = bool(props['bIsDeprecated'][3]) if 'bIsDeprecated' in props else False
    return r


def humanize(n):
    n = re.sub(r'^D_', '', n).replace('_', ' ')
    return re.sub(r'(?<=[a-z])(?=[A-Z0-9])|(?<=[0-9])(?=[A-Z])', ' ', n).strip()


# table -> category id (labels live in the UI)
CATS = {'Weapons': 'weapon', 'Clothing': 'armor', 'Resources': 'resource', 'Consumables': 'consumable', 'Augments': 'augment',
        'Schematics': 'schematic', 'Customizations': 'cosmetic', 'Placeables': 'placeable', 'Vehicles': 'vehicle',
        'MiscEquipment': 'equipment', 'Gadgets': 'gadget', 'ItemMods': 'mod', 'Contracts': 'contract', 'Emotes': 'emote',
        'BuildingSets': 'building', 'BuildingBlueprints': 'building'}


def main(src, loc_path=None):
    loc = json.load(open(loc_path, encoding='utf-8')) if loc_path else {}
    items = {}
    for f in sorted(os.listdir(src)):
        m = re.match(r'DT_BaseItems_(\w+)\.uasset$', f)
        if not m: continue
        a = open(os.path.join(src, f), 'rb').read(); x = open(os.path.join(src, f[:-7] + '.uexp'), 'rb').read()
        n, rows = read_table(a, x)
        for rid, props in rows.items():
            r = row_info(x, n, props)
            if r['dep'] or rid in items: continue
            tags = r.get('tags', [])
            tier = next((int(t.split('.')[1]) for t in tags if re.fullmatch(r'LootTier\.\d+', t)), None)
            rar = next((t.split('.')[1] for t in tags if t.startswith('Rarity.')), None)
            grp = next((t[6:] for t in tags if t.startswith('Items.') and not re.match(r'Items\.(Exclude|Hide|NotCust|ActorBound)', t)), '')
            name = loc.get(r.get('Name') or '')
            e = {'n': (name or humanize(rid)).strip(), 'c': CATS.get(m.group(1), 'misc'), 'm': max(1, r.get('MaxStackSize', 1)),
                 'g': grp}
            if m.group(1) == 'Weapons':                       # this table also holds ammo and hand tools
                e['c'] = 'ammo' if grp.startswith('Ammo') else 'weapon' if re.match(r'Holsters\.(Ranged|Melee)Weapons', grp) else 'tool'
            if not name: e['u'] = 1                           # no in-game name found: shown as a tidied-up id
            if tier is not None: e['t'] = tier
            if rar: e['r'] = rar
            if r.get('MaxDurability', 0) > 0: e['d'] = 1
            if r.get('bIsEnabled') == 0: e['off'] = 1
            if 'MaxQuantity' in r and r['MaxQuantity'] > 0: e['mq'] = r['MaxQuantity']
            items[rid] = e
    out = os.path.join(ROOT, 'data', 'items.json')
    json.dump(items, open(out, 'w', encoding='utf-8'), separators=(',', ':'), sort_keys=True)
    from collections import Counter
    print(len(items), 'items', dict(Counter(v['c'] for v in items.values())), 'unnamed', sum('u' in v for v in items.values()))


if __name__ == '__main__':
    if len(sys.argv) < 2: raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
