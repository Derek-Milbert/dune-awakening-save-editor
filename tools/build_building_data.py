"""Build data/building.json (every building set + its pieces) from the game's DT_BuildableUnlockableSetsData and
ST_Localization_Buildings, both extracted with retoc (`retoc to-legacy -f <name> <Paks> <out>`).
usage: python tools/build_building_data.py <dir with DT_BuildableUnlockableSetsData.*> <dir with ST_Localization_Buildings.*>
The data table uses tagged properties: each row is (row-name FName)(m_Buildables SetProperty ...)(set of piece FNames)."""
import json, os, re, struct, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find(d, name):
    for dp, _, fs in os.walk(d):
        if name in fs: return os.path.join(dp, name)
    raise SystemExit(f'{name} not found under {d}')


def read_names(a):
    """name map: int32 length + NUL-terminated string + 4 hash bytes, starting at the first (alphabetical) name."""
    p = a.find(b'Advanced_SurvivalFabricator_Placeable') - 4; names = []
    while True:
        n = struct.unpack_from('<i', a, p)[0]
        if not (0 < n < 300) or a[p + 4 + n - 1] != 0: break
        names.append(a[p + 4:p + 4 + n - 1].decode()); p += 4 + n + 4
    return names


def read_rows(a, x):
    names = read_names(a); mb = names.index('m_Buildables'); rows = {}
    for q in range(8, len(x) - 8):
        if struct.unpack_from('<ii', x, q) != (mb, 0): continue
        rn, rnum = struct.unpack_from('<ii', x, q - 8)
        if not (0 <= rn < len(names)) or rnum != 0: continue
        pieces = []
        for o in range(q + 16, q + 80):                      # skip the tag; find (removed=0, count, FNames...)
            rem, cnt = struct.unpack_from('<ii', x, o)
            if rem != 0 or not 1 <= cnt <= 1000 or o + 8 + cnt * 8 > len(x): continue
            els = [struct.unpack_from('<ii', x, o + 8 + 8 * i) for i in range(cnt)]
            if all(0 <= i < len(names) and n == 0 for i, n in els): pieces = [names[i] for i, _ in els]; break
        rows[names[rn]] = pieces
    return rows


def read_fstrings(d):
    out = []; i = 0; n = len(d)
    while i < n - 4:
        ln = struct.unpack_from('<i', d, i)[0]; s = None
        if 2 <= ln <= 4000 and i + 4 + ln <= n and d[i + 3 + ln] == 0:
            b = d[i + 4:i + 3 + ln]
            if all(c >= 32 or c in (10, 13, 9) for c in b):
                try: s = b.decode('utf-8'); step = 4 + ln
                except UnicodeDecodeError: s = None
        elif -4000 <= ln <= -2 and i + 4 + (-ln) * 2 <= n:
            b = d[i + 4:i + 4 + (-ln) * 2]
            if b[-2:] == b'\x00\x00':
                try: s = b[:-2].decode('utf-16le'); step = 4 + (-ln) * 2
                except UnicodeDecodeError: s = None
        if s is not None: out.append(s); i += step
        else: i += 1
    return out


def humanize(n):
    n = re.sub(r'_?(Patent|Placeable)$', '', n).replace('_', ' ')
    return re.sub(r'(?<=[a-z])(?=[A-Z0-9])|(?<=[0-9])(?=[A-Z])', ' ', n).strip()


def main(tbl_dir, loc_dir):
    a = open(find(tbl_dir, 'DT_BuildableUnlockableSetsData.uasset'), 'rb').read()
    x = open(find(tbl_dir, 'DT_BuildableUnlockableSetsData.uexp'), 'rb').read()
    rows = read_rows(a, x)
    fs = read_fstrings(open(find(loc_dir, 'ST_Localization_Buildings.uexp'), 'rb').read()); loc = {}
    for k, v in zip(fs, fs[1:]):
        if re.match(r'^[A-Za-z0-9_]+/[A-Za-z0-9_.\-]+$', k) and k not in loc: loc[k] = v
    def lname(n): return loc.get('BUILDINGS/' + n.upper())
    sets = {}; pieces = {}
    for sid, pcs in rows.items():
        key = 'BUILDINGS/BUILDING_SET_' + sid.upper()
        name = loc.get(key + '_NAME') or loc.get(key + '_SHORTDESC') or humanize(sid)
        short = loc.get(key + '_SHORTDESC', '')
        sets[sid] = {'name': name.strip(), 'desc': short.strip() if short.strip() != name.strip() else '', 'pieces': pcs,
                     'named': (key + '_NAME') in loc}
        for p in pcs: pieces.setdefault(p, lname(p) or humanize(p))
    out = {'sets': sets, 'pieces': dict(sorted(pieces.items()))}
    json.dump(out, open(os.path.join(ROOT, 'data', 'building.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print(f'{len(sets)} sets ({sum(s["named"] for s in sets.values())} with game names), {len(pieces)} pieces '
          f'({sum(1 for p in pieces if lname(p))} with game names)')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
