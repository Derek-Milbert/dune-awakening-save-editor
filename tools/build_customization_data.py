"""Build data/customization.json (every skin = mesh/material variant and every swatch) from the game's
Systems/Customization data assets, extracted with retoc:
    retoc to-legacy --no-shaders -f "Dune/Systems/Customization/" <Paks> <out>
usage: python tools/build_customization_data.py <out dir> [items_st.json]
(items_st.json = ST_Localization_Items key -> text, used for display names.)
Each CustomizationVariantData / CustomizationSwatchData asset has a name-typed m_Identifier; that identifier is what the
save stores in m_UnlockedCustomizationIds. The assets use unversioned properties, so the identifier is the one plain
name in the asset's name table that is not a path, property/class name, tag or DA_ asset name."""
import json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIX = ('/', 'm_', 'DA_', 'Default__', 'Customization', 'Items.', 'T_', 'SK_', 'SM_', 'MI_', 'M_')
STRUCT = {'None', 'Class', 'Package', 'Object', 'GameplayTag', 'GameplayTagContainer', 'LinearColor', 'StringTable', 'Materials',
          'MeshOverride', 'StaticMeshAttachSocketOverride', 'ST_Localization_Items', 'ST_Localization_UI', 'Color'}


def strings(path):
    """printable strings of the .uasset and (if present) its .uexp"""
    out = []
    for ext in ('.uasset', '.uexp'):
        q = os.path.splitext(path)[0] + ext
        if os.path.exists(q): out += [m.decode('latin1') for m in re.findall(rb'[\x20-\x7e]{3,}', open(q, 'rb').read())]
    return out


def ident(names):
    return [n for n in names if not (n.startswith(PREFIX) or n.endswith('Property') or n in STRUCT or '.' in n or n.count(' ') > 2)]


def clean(t):
    return re.sub(r'^[^\w(]+', '', t.strip())     # some strings carry a stray leading length character


def humanize(n):
    n = re.sub(r'(_MeshVariant|_MeshData|_Variant|Variant$)', '', n).replace('_', ' ')
    return re.sub(r'(?<=[a-z])(?=[A-Z0-9])|(?<=[0-9])(?=[A-Z])', ' ', n).strip()


def main(root, st_path=None):
    loc = json.load(open(st_path, encoding='utf-8')) if st_path else {}
    base = None
    for dp, _, _ in os.walk(root):
        if dp.replace(os.sep, '/').endswith('Dune/Systems/Customization'): base = dp; break
    if not base: raise SystemExit('Dune/Systems/Customization not found under ' + root)
    content = os.path.dirname(os.path.dirname(os.path.dirname(base)))   # .../Content
    out = []; amb = []
    for dp, _, fs in os.walk(base):
        for f in sorted(fs):
            if not f.endswith('.uasset'): continue
            p = os.path.join(dp, f); rel = os.path.relpath(p, base).replace(os.sep, '/')
            names = strings(p)
            kind = 'swatch' if 'CustomizationSwatchData' in names else 'skin' if 'CustomizationVariantData' in names else None
            if not kind: continue
            cand = ident(names)
            if len(cand) != 1: amb.append((rel, cand)); continue
            tags = sorted({n for n in names if n.startswith(('Items.', 'Customization.'))})
            gui = next((n for n in names if n.startswith('/Game/') and '/DA_GUI_' in n and not n.endswith(f[:-7])), None)
            name = desc = ''
            if gui:
                g = os.path.join(content, *gui[len('/Game/'):].split('/')) + '.uasset'
                keys = [k for s in strings(g) for k in re.findall(r'ITEMS/[A-Z0-9_.\-]+', s)] if os.path.exists(g) else []   # FString keys carry a length byte
                nk = next((k for k in keys if k.endswith('_NAME')), None); dk = next((k for k in keys if k.endswith('_DESC')), None)
                name = clean(loc.get(nk, '')) if nk else ''; desc = clean(loc.get(dk, '')) if dk else ''
            placeable = any(t.startswith('Customization.Placeables') for t in tags)
            domain = ('armor' if rel.startswith('Clothing/') else 'weapon' if rel.startswith('Weapons/')
                      else 'placeable' if placeable else 'vehicle' if rel.startswith('Vehicles/') or any(t.startswith('Customization.Vehicle') for t in tags) else 'other')
            out.append({'id': cand[0], 'kind': kind, 'domain': domain, 'name': name.strip() or humanize(cand[0]), 'named': bool(name.strip()),
                        'desc': desc.strip(), 'tags': [t for t in tags if t.startswith('Items.')], 'folder': rel.rsplit('/', 1)[0] if '/' in rel else ''})
    seen = {}
    for e in out: seen.setdefault(e['id'], e)          # the same identifier in two assets: keep the first
    res = sorted(seen.values(), key=lambda e: (e['domain'], e['kind'], e['name'].lower(), e['id']))
    json.dump(res, open(os.path.join(ROOT, 'data', 'customization.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print(f'{len(res)} entries ({sum(e["kind"] == "skin" for e in res)} skins, {sum(e["kind"] == "swatch" for e in res)} swatches); '
          f'{sum(e["named"] for e in res)} with game names; {len(out) - len(res)} duplicate ids; {len(amb)} ambiguous assets skipped')
    for r in amb[:15]: print('  ambiguous:', r)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
