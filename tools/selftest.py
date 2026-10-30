"""Self-test on a COPY of a save. usage: python tools/selftest.py <path to real game.db>"""
import os, sys, shutil, tempfile, sqlite3
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pathlib import Path
from dune_editor import savefile, editors, fmt

work = Path(tempfile.mkdtemp(prefix='dune_selftest_'))
(work / 'acct').mkdir()
copy = work / 'acct' / 'game.db'
shutil.copy2(sys.argv[1], copy)
orig_bytes = copy.read_bytes()
s = savefile.Save(copy, work / 'backups')
c = s.conn
ov = editors.overview(c); print('overview: level', ov['level'], '| currencies', [x['balance'] for x in ov['currency']])   # no names / ids, safe to paste in bug reports

# 1. no-op round trip must leave every blob identical
a_before = c.execute('select properties from actors where id=?', (editors.ids(c)['pawn'],)).fetchone()[0]
e_before = c.execute('select components from fgl_entities where entity_id=?', (editors._entity_id(c),)).fetchone()[0]
editors.set_skills(c, ranks={}); editors.set_recipes(c, [])
a_after = c.execute('select properties from actors where id=?', (editors.ids(c)['pawn'],)).fetchone()[0]
e_after = c.execute('select components from fgl_entities where entity_id=?', (editors._entity_id(c),)).fetchone()[0]
assert a_before == a_after and e_before == e_after, 'no-op edit changed bytes'
print('no-op edits leave actor + entity blobs byte-identical: OK')

# 2. real edits
rec_before = {(r['id'], r['grade']): r['count'] for r in editors.get_recipes(c)}
editors.set_currency(c, {0: 123456789, 1: 5000000})
editors.set_skills(c, ranks={'Skills.Attribute.Weaponry1': 3, 'Skills.Key.Trooper2': 1, 'Skills.Ability.Whirlwind': 1},
                   total_points=300, unspent_points=250)
editors.set_spec(c, levels={1: 100, 4: 80.5}, keystones=['Combat_CombatKeystone_SkillPoint1', 'Crafting_CraftingKeystone_RangedWeaponAugmentSlots1'])
r = editors.set_recipes(c, [{'id': 'Kindjal_Unique_Blood_06_recipe', 'grade': 5, 'count': 7},
                            {'id': 'T6_Augment_smg1_Recipe', 'grade': 5, 'count': 4}])
print('recipes:', r)
editors.set_tech_points(c, 9999)
# skins & swatches, building sets, inventory
from dune_editor import changes
orig = s.original(); base = changes.snapshot(orig); orig.close()
cust_before = editors.get_customization(c)
cust_cat = [e['id'] for e in editors.load_json('customization.json')]
cust_new = [x for x in cust_cat if x not in cust_before]
editors.set_customization(c, cust_before + cust_new[:5])
sets_before = editors.get_building(c)['sets']
set_cat = list(editors.load_json('building.json')['sets'])
editors.set_building(c, sets=sorted(set(sets_before) | set(set_cat[:3])))
bp = next(g for g in editors.get_inventory(c) if g['type'] == 0)
alu_before = sum(i['qty'] for i in bp['items'] if i['template'] == 'AluminiumBar')
editors.apply_inventory(c, [{'op': 'add', 'inv': bp['id'], 'template': 'AluminiumBar', 'qty': 750}])
groups = {g['area'] for g in changes.diff(base, changes.snapshot(c))}
assert {'Wallet', 'Inventory'} <= groups, groups
print('pending-changes areas:', sorted(groups))
res = s.write()
print('write ->', res)
s.close()

# 3. re-open from disk and verify
s2 = savefile.Save(copy, work / 'backups')
c2 = s2.conn
assert [x['balance'] for x in editors.get_currency(c2)] == [123456789, 5000000]
sk = editors.get_skills(c2)
assert sk['ranks']['Skills.Attribute.Weaponry1'] == 3 and sk['ranks']['Skills.Key.Trooper2'] == 1 and sk['ranks']['Skills.Ability.Whirlwind'] == 1
assert sk['total_points'] == 300 and sk['unspent_points'] == 250 and sk['level'] == 301
sp = editors.get_spec(c2)
t = {x['track']: x for x in sp['tracks']}
assert t[1]['level'] == 100 and t[1]['xp'] == 44182 and t[4]['level'] == 80.5, t
assert {k['name'] for k in sp['keystones'] if k['owned']} == {'Combat_CombatKeystone_SkillPoint1', 'Crafting_CraftingKeystone_RangedWeaponAugmentSlots1'}
rec_after = {(r['id'], r['grade']): r['count'] for r in editors.get_recipes(c2)}
assert rec_after[('Kindjal_Unique_Blood_06_recipe', 5)] == 7 and rec_after[('T6_Augment_smg1_Recipe', 5)] == 4
changed = {k for k in set(rec_before) | set(rec_after) if rec_before.get(k) != rec_after.get(k)}
assert changed == {('Kindjal_Unique_Blood_06_recipe', 5), ('T6_Augment_smg1_Recipe', 5)}, changed
assert editors.get_tech_points(c2) == 9999
assert set(editors.get_customization(c2)) == set(cust_before) | set(cust_new[:5])
assert set(editors.get_building(c2)['sets']) >= set(set_cat[:3])
bp2 = next(g for g in editors.get_inventory(c2) if g['type'] == 0)
assert sum(i['qty'] for i in bp2['items'] if i['template'] == 'AluminiumBar') == alu_before + 750
print('all edits read back correctly after a full write + re-open: OK')
print('backups made:', [b['name'] for b in savefile.list_backups(work / 'backups')])
print('integrity:', c2.execute('pragma integrity_check').fetchone()[0])
s2.close()
shutil.rmtree(work, ignore_errors=True)
print('SELFTEST PASSED; your real save was only read, never written.')
