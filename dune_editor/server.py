"""Tiny local web server: JSON API + static UI. Binds to 127.0.0.1 only."""
from __future__ import annotations

import json
import mimetypes
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import changes, editors, savefile
from .editors import EditError, load_json
from .savefile import Save, SaveError

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / 'web'
BACKUPS = ROOT / 'backups'
LOCK = threading.RLock()


class App:
    save: Save | None = None


def _state():
    saves = savefile.find_saves()
    out = {'saves': saves, 'running': savefile.game_running(), 'open': None, 'dirty': False}
    if App.save:
        out['open'] = str(App.save.path)
        out['dirty'] = App.save.dirty
        out['overview'] = editors.overview(App.save.conn)
    return out


def _need_save():
    if not App.save:
        raise EditError('no save is open')
    return App.save


def route_get(path, q):
    if path == '/api/state':
        return _state()
    if path == '/api/skills':
        s = _need_save()
        return {'catalog': load_json('skills.json'), 'state': editors.get_skills(s.conn)}
    if path == '/api/spec':
        return editors.get_spec(_need_save().conn)
    if path == '/api/recipes':
        s = _need_save()
        return {'catalog': load_json('recipes.json'), 'known': editors.get_recipes(s.conn)}
    if path == '/api/building':
        return {**editors.get_building(_need_save().conn), 'catalog': load_json('building.json')}
    if path == '/api/customization':
        return {'catalog': load_json('customization.json'), 'owned': editors.get_customization(_need_save().conn)}
    if path == '/api/inventory':
        return {'catalog': editors.load_json('items.json'), 'inventories': editors.get_inventory(_need_save().conn)}
    if path == '/api/summary':
        return changes.summary(_need_save().conn)
    if path == '/api/changes':
        s = _need_save()
        orig = s.original()
        try:
            base = changes.snapshot(orig)
        finally:
            orig.close()
        return {'groups': changes.diff(base, changes.snapshot(s.conn))}
    if path == '/api/backups':
        return {'backups': savefile.list_backups(BACKUPS)}
    raise EditError('unknown endpoint')


def route_post(path, body):
    if path == '/api/open':
        with LOCK:
            if App.save:
                App.save.close()
                App.save = None
            known = {s['path'] for s in savefile.find_saves()}
            p = body.get('path', '')
            if p not in known:
                raise EditError('that is not a detected save')
            App.save = Save(p, BACKUPS)
        return _state()
    s = _need_save()
    c = s.conn
    if path == '/api/currency':
        editors.set_currency(c, body.get('balances', {}))
    elif path == '/api/tech':
        editors.set_tech_points(c, body['value'])
    elif path == '/api/skills':
        editors.set_skills(c, ranks=body.get('ranks'), total_points=body.get('total_points'),
                           unspent_points=body.get('unspent_points'), total_xp=body.get('total_xp'))
    elif path == '/api/spec':
        editors.set_spec(c, levels=body.get('levels'), keystones=body.get('keystones'))
    elif path == '/api/recipes':
        res = editors.set_recipes(c, body.get('items', []))
        s.dirty = True
        return res
    elif path == '/api/customization':
        res = editors.set_customization(c, body.get('owned', []))
        s.dirty = True
        return res
    elif path == '/api/inventory':
        res = editors.apply_inventory(c, body.get('ops', []))
        s.dirty = True
        return res
    elif path == '/api/building':
        editors.set_building(c, sets=body.get('sets'), pieces=body.get('pieces'))
    elif path == '/api/discard':
        s.reload()
        return _state()
    elif path == '/api/write':
        res = s.write()
        return {'result': res, 'state': _state()}
    elif path == '/api/backup':
        return {'backup': str(s.backup(body.get('label', 'manual')))}
    elif path == '/api/restore':
        d = BACKUPS / body.get('name', '')
        if d.parent != BACKUPS or not (d / 'ORIGIN.txt').exists():
            raise EditError('unknown backup')
        running = savefile.game_running()
        if running:
            raise EditError('Dune: Awakening is running (' + ', '.join(running) + '). Close it completely, then try again.')
        s.backup('before_restore')
        savefile.restore_backup(d)
        s.reload()
        return _state()
    else:
        raise EditError('unknown endpoint')
    s.dirty = True
    return {'ok': True, 'state': _state()}


class Handler(BaseHTTPRequestHandler):
    server_version = 'DuneEditor/0.1'

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        data = json.dumps(obj).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self):
        host = (self.headers.get('Host') or '').split(':')[0]
        return host in ('127.0.0.1', 'localhost')

    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {'error': 'bad host'})
        u = urlparse(self.path)
        if u.path.startswith('/api/'):
            try:
                with LOCK:
                    return self._json(200, route_get(u.path, u.query))
            except (EditError, SaveError) as e:
                return self._json(400, {'error': str(e)})
            except Exception as e:
                traceback.print_exc()
                return self._json(500, {'error': f'{type(e).__name__}: {e}'})
        rel = 'index.html' if u.path in ('/', '') else u.path.lstrip('/')
        f = (WEB / rel).resolve()
        if WEB.resolve() not in f.parents and f != WEB.resolve() or not f.is_file():
            self.send_error(404)
            return
        data = f.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', (mimetypes.guess_type(f.name)[0] or 'application/octet-stream') + '; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if not self._host_ok() or self.headers.get('X-Dune-Editor') != '1':
            return self._json(403, {'error': 'forbidden'})
        n = int(self.headers.get('Content-Length') or 0)
        try:
            body = json.loads(self.rfile.read(n) or b'{}')
        except ValueError:
            return self._json(400, {'error': 'bad json'})
        try:
            with LOCK:
                return self._json(200, route_post(urlparse(self.path).path, body))
        except (EditError, SaveError) as e:
            return self._json(400, {'error': str(e)})
        except Exception as e:
            traceback.print_exc()
            return self._json(500, {'error': f'{type(e).__name__}: {e}'})


def serve(port=8765, open_browser=True):
    BACKUPS.mkdir(exist_ok=True)
    srv = None
    for p in range(port, port + 20):
        try:
            srv = ThreadingHTTPServer(('127.0.0.1', p), Handler)
            port = p
            break
        except OSError:
            continue
    if srv is None:
        raise SystemExit('could not find a free port')
    url = f'http://127.0.0.1:{port}/'
    print(f'Dune: Awakening Save Editor running at {url}  (Ctrl+C to stop)')
    saves = savefile.find_saves()
    print(f'Found {len(saves)} save(s):', *(s['path'] for s in saves), sep='\n  ')
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if App.save:
            App.save.close()
