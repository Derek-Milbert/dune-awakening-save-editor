"""Read-only dump of what an editor-written save contains. usage: python tools/inspect_save.py <game.db>"""
import os, sys, tempfile, shutil
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pathlib import Path
from dune_editor import savefile, editors

tmp = Path(tempfile.mkdtemp()); (tmp / 'a').mkdir(); shutil.copy2(sys.argv[1], tmp / 'a' / 'game.db')
s = savefile.Save(tmp / 'a' / 'game.db', tmp / 'b'); c = s.conn
print('integrity:', c.execute('pragma integrity_check').fetchone()[0])
print('currency:', editors.get_currency(c), '| tech:', editors.get_tech_points(c))
sk = editors.get_skills(c)
print('skills: total', sk['total_points'], 'unspent', sk['unspent_points'], 'ranked nodes', sum(1 for v in sk['ranks'].values() if v))
print('  Planetologist nodes ranked:', sorted(k.split('.', 1)[1] for k, v in sk['ranks'].items() if v and ('Planetologist' in k or 'Scientist' in k or 'Explorer' in k or 'Driver' in k)))
sp = editors.get_spec(c)
print('spec tracks:', [(t['name'], t['level'], t['xp']) for t in sp['tracks']])
print('traits owned:', sum(k['owned'] for k in sp['keystones']), 'of', len(sp['keystones']))
rec = editors.get_recipes(c)
print('known recipe entries:', len(rec))
s.close(); shutil.rmtree(tmp, ignore_errors=True)
