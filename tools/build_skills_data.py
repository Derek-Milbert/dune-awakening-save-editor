"""Build data/skills.json (class skill catalogue) from a save + the extracted localization strings.
usage: python tools/build_skills_data.py <game.db>
"""
import sys, os, re, json, zlib, sqlite3, tempfile
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from dune_editor import fmt

CLASSES = [
    ('Trooper',      'TR', [('Weaponry', 'Gunnery'), ('SuspensorTech', 'Suspensor Training'), ('Gadgets', 'Tactical Tech')]),
    ('Mentat',       'ME', [('MentalCalculus', 'Mental Calculus'), ('Assassination', 'Assassination'), ('Tactician', 'Tactician')]),
    ('Planetologist', 'PL', [('Scientist', 'Scientist'), ('Explorer', 'Explorer'), ('Driver', 'Mechanic')]),
    ('BeneGesserit', 'BG', [('WeirdingWay', 'Weirding Way'), ('Manipulation', 'The Voice'), ('SelfControl', 'Body Control')]),
    ('Swordmaster',  'SM', [('Blade', 'The Blade'), ('Resolve', 'The Will'), ('Aggression', 'The Way')]),
]
CLASS_LABEL = {'BeneGesserit': 'Bene Gesserit'}
MAX_RANK = {'Key': 1, 'Attribute': 3, 'Ability': 3, 'Perk': 1, 'Spice': 1}

d = open(sys.argv[1], 'rb').read()
raw = zlib.decompress(d[8:])
f = os.path.join(tempfile.mkdtemp(), 'x.sqlite'); open(f, 'wb').write(raw)
c = sqlite3.connect('file:' + f.replace('\\', '/') + '?mode=ro', uri=True)
b = c.execute('select components from fgl_entities where entity_id=8499249849353389514').fetchone()[0]
lc = fmt.decode(b).get('FLevelComponent').value[1]
tags = [re.search(r'"([^"\\]+)', k).group(1) for k, _ in lc.get('ModuleData').value]

loc = json.load(open(os.path.join(ROOT, '_work', 'loc_skills.json')))['ST_Localization_Abilities']

def toks(s):
    s = re.sub(r'([a-z])([A-Z])', r'\1 \2', s)
    return [t for t in re.split(r'[^A-Za-z]+', s.lower()) if t]
SYN = {'grenade': 'bomb', 'riposte': 'riposte', 'compel': 'compel'}
def norm(ts): return {SYN.get(t, t) for t in ts}

ability_loc = {}
for k, v in loc.items():
    m = re.match(r'SKILLS/(ABILITIES|TECHNIQUE|SPICE)_(.+)_(NAME)$', k)
    if m:
        base = m.group(2)
        ability_loc[(m.group(1), base)] = {'name': v, 'short': loc.get(k.replace('_NAME', '_SHORTDESC'), ''), 'long': loc.get(k.replace('_NAME', '_LONGDESC'), '')}

def lookup(kind, tag):
    last = tag.split('.', 2)[2]
    want = norm(toks(last))
    best, score = None, 0
    for (grp, base), info in ability_loc.items():
        if kind == 'Spice' and grp != 'SPICE': continue
        have = norm(toks(base.replace('-', ' ')))
        if not have: continue
        s = len(want & have) / len(want | have)
        if s > score: best, score = info, s
    return best if score >= 0.5 else None

cls_of_tree = {}
tree_label = {}
for cname, code, trees in CLASSES:
    for key, label in trees:
        cls_of_tree[key] = cname; tree_label[key] = label

def pretty(s):
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', s.replace('_', ' ')).strip()

nodes = []
for tag in tags:
    _, kind, last = tag.split('.', 2)
    n = {'tag': tag, 'kind': kind, 'max': MAX_RANK.get(kind, 1), 'name': pretty(last), 'short': '', 'long': '', 'class': None, 'tree': None, 'role': None}
    if kind == 'Key':
        m = re.fullmatch(r'(Trooper|Mentat|Planetologist|BeneGesserit|Swordmaster)(\d)', last)
        if m:
            n.update({'class': m.group(1), 'role': 'gate', 'order': int(m.group(2)), 'name': f"{CLASS_LABEL.get(m.group(1), m.group(1))} tier {m.group(2)}"})
        else:
            t = last.replace('Capstone', '')
            if t in cls_of_tree:
                n.update({'class': cls_of_tree[t], 'tree': t, 'role': 'capstone', 'name': f'{tree_label[t]} capstone'})
    elif kind == 'Attribute':
        m = re.fullmatch(r'([A-Za-z]+?)(\d+)', last)
        t = m.group(1) if m else last
        if t in cls_of_tree:
            n.update({'class': cls_of_tree[t], 'tree': t, 'role': 'node', 'order': int(m.group(2)), 'name': f'{tree_label[t]} · node {m.group(2)}'})
        else:
            n.update({'class': 'Swordmaster', 'tree': 'Blade', 'role': 'node', 'order': 99, 'name': pretty(last)})
    else:
        info = lookup(kind, tag)
        if info and not info['name'].startswith('XX_') and info['name'] != 'Ignore':
            n.update({'name': info['name'], 'short': info['short'], 'long': info['long']})
    nodes.append(n)

out = {
    'classes': [{'id': c, 'label': CLASS_LABEL.get(c, c), 'trees': [{'id': k, 'label': l} for k, l in tr]} for c, _, tr in CLASSES],
    'nodes': nodes,
    'max_rank': MAX_RANK,
}
os.makedirs(os.path.join(ROOT, 'data'), exist_ok=True)
json.dump(out, open(os.path.join(ROOT, 'data', 'skills.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
named = sum(1 for n in nodes if n['short'] or n['long'])
print(len(nodes), 'nodes;', named, 'with game descriptions')
import collections
print(collections.Counter((n['class'], n['role']) for n in nodes))
print('unassigned abilities/perks/spice:', [n['name'] for n in nodes if n['class'] is None][:80])
