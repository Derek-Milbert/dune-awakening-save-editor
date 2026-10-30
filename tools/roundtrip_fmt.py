import sys, os, zlib, sqlite3, tempfile
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dune_editor import fmt

d = open(sys.argv[1], 'rb').read()
raw = zlib.decompress(d[8:])
f = os.path.join(tempfile.mkdtemp(), 'x.sqlite'); open(f, 'wb').write(raw)
c = sqlite3.connect('file:' + f.replace('\\', '/') + '?mode=ro', uri=True)

tests = []
for (aid, blob) in c.execute('select id, properties from actors where properties is not null'):
    tests.append((f'actors.properties id={aid}', blob))
for (eid, blob) in c.execute('select entity_id, components from fgl_entities where components is not null'):
    tests.append((f'fgl_entities {eid}', blob))
ok = bad = err = 0; sizes = 0
fails = []
for name, blob in tests:
    if len(blob) < 2: continue
    try:
        n = fmt.decode(blob)
        again = fmt.encode(n)
        if again == blob: ok += 1; sizes += len(blob)
        else:
            bad += 1; fails.append((name, 'mismatch', len(blob), len(again)))
    except Exception as e:
        err += 1; fails.append((name, repr(e)[:90], len(blob)))
print(f'blobs tested {ok+bad+err}: identical round-trip {ok} ({sizes} bytes), mismatch {bad}, decode errors {err}')
for x in fails[:15]: print('  ', x)
