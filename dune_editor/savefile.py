"""Locate, open, back up and write the Dune: Awakening solo save (game.db).

game.db = 8-byte header (u32 flag=1, u32 uncompressed size) + zlib stream of a SQLite database.
"""
from __future__ import annotations

import datetime
import os
import shutil
import sqlite3
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path

HEADER = struct.Struct('<II')
GAME_PROCESSES = ('DuneSandbox', 'DuneSandbox-Win64-Shipping')


class SaveError(Exception):
    pass


def save_roots() -> list[Path]:
    override = os.environ.get('DUNE_EDITOR_SAVE_ROOT')     # point the editor at a test copy of PlayerClientStorage
    if override:
        return [Path(override)]
    local = os.environ.get('LOCALAPPDATA')
    roots = []
    if local:
        roots.append(Path(local) / 'DuneSandbox' / 'Saved' / 'Cloud' / 'PlayerClientStorage')
    return roots


def find_saves() -> list[dict]:
    """Every game.db under PlayerClientStorage/<env>/<account>/, newest first."""
    found = []
    for root in save_roots():
        if not root.exists():
            continue
        for db in root.glob('*/*/game.db'):
            st = db.stat()
            found.append({
                'path': str(db),
                'folder': str(db.parent),
                'environment': db.parent.parent.name,
                'account': db.parent.name,
                'size': st.st_size,
                'modified': datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec='seconds'),
            })
    found.sort(key=lambda x: x['modified'], reverse=True)
    return found


def game_running() -> list[str]:
    """Names of running Dune: Awakening processes (empty list = safe to write)."""
    try:
        out = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=20).stdout
    except Exception:
        return []
    names = set()
    for line in out.splitlines():
        parts = line.strip().strip('"').split('","')
        if parts and parts[0].lower().removesuffix('.exe') in {p.lower() for p in GAME_PROCESSES}:
            names.add(parts[0])
    return sorted(names)


def read_db(path: Path) -> bytes:
    data = Path(path).read_bytes()
    if len(data) < 16:
        raise SaveError('game.db is too small to be a save')
    flag, usize = HEADER.unpack(data[:8])
    if flag != 1:
        raise SaveError(f'unexpected game.db header flag {flag}; the save format may have changed')
    raw = zlib.decompress(data[8:])
    if len(raw) != usize:
        raise SaveError('game.db size field does not match its contents')
    if raw[:15] != b'SQLite format 3':
        raise SaveError('game.db does not contain a SQLite database')
    return raw


def pack_db(raw: bytes) -> bytes:
    return HEADER.pack(1, len(raw)) + zlib.compress(raw, 6)


class Save:
    """An open save: edits are made on a temporary copy and only written back by write()."""

    def __init__(self, path: str | Path, backup_root: Path):
        self.path = Path(path)
        self.backup_root = Path(backup_root)
        self.workdir = Path(tempfile.mkdtemp(prefix='dune_edit_'))
        self.dbfile = self.workdir / 'game.sqlite'
        self.conn: sqlite3.Connection | None = None
        self.dirty = False
        self.source_mtime = None
        self._open()

    # ---- lifecycle ------------------------------------------------------
    def _open(self):
        raw = read_db(self.path)
        self.source_mtime = self.path.stat().st_mtime
        self.dbfile.write_bytes(raw)
        self.origfile = self.workdir / 'orig.sqlite'      # untouched copy, used to list the staged changes
        self.origfile.write_bytes(raw)
        # requests are served from worker threads; server.py serializes all access with one lock
        self.conn = sqlite3.connect(str(self.dbfile), check_same_thread=False)
        self.conn.execute('PRAGMA journal_mode=DELETE')
        ok = self.conn.execute('PRAGMA integrity_check').fetchone()[0]
        if ok != 'ok':
            raise SaveError(f'save failed its integrity check: {ok}')
        self.dirty = False

    def original(self):
        """read-only connection to the save as it was when opened / last written"""
        return sqlite3.connect(f'file:{self.origfile.as_posix()}?mode=ro', uri=True)

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
        shutil.rmtree(self.workdir, ignore_errors=True)

    def reload(self):
        if self.conn:
            self.conn.close()
        self._open()

    # ---- backups ----------------------------------------------------------
    def backup(self, label: str = 'manual') -> Path:
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        dest = self.backup_root / f'{stamp}_{label}'
        dest.mkdir(parents=True, exist_ok=False)
        src = self.path.parent
        shutil.copytree(src, dest / src.name)
        (dest / 'ORIGIN.txt').write_text(str(src), encoding='utf-8')
        n_src = sum(1 for _ in src.rglob('*') if _.is_file())
        n_dst = sum(1 for _ in (dest / src.name).rglob('*') if _.is_file())
        if n_src != n_dst:
            raise SaveError('backup is incomplete; nothing was written')
        return dest

    # ---- write ------------------------------------------------------------
    def write(self) -> dict:
        running = game_running()
        if running:
            raise SaveError('Dune: Awakening is running (' + ', '.join(running) + '). Close it completely, then try again.')
        if self.path.stat().st_mtime != self.source_mtime:
            raise SaveError('game.db changed on disk since it was opened (the game saved?). Re-open the save and redo your edits.')
        self.conn.commit()
        ok = self.conn.execute('PRAGMA integrity_check').fetchone()[0]
        if ok != 'ok':
            raise SaveError(f'edited database failed its integrity check: {ok}')
        self.conn.close()
        raw = self.dbfile.read_bytes()
        assert raw[:15] == b'SQLite format 3'
        backup = self.backup('before_write')
        tmp = self.path.with_name('game.db.editor_tmp')
        try:
            tmp.write_bytes(pack_db(raw))
            read_db(tmp)                      # must decode again before it replaces the real file
            os.replace(tmp, self.path)
        finally:
            if tmp.exists():
                tmp.unlink()
        self.reload()
        return {'backup': str(backup), 'bytes': self.path.stat().st_size}


def list_backups(backup_root: Path) -> list[dict]:
    out = []
    if backup_root.exists():
        for d in sorted(backup_root.iterdir(), reverse=True):
            if d.is_dir() and (d / 'ORIGIN.txt').exists():
                size = sum(f.stat().st_size for f in d.rglob('*') if f.is_file())
                out.append({'name': d.name, 'path': str(d), 'origin': (d / 'ORIGIN.txt').read_text(encoding='utf-8'), 'bytes': size})
    return out


def restore_backup(backup_dir: Path):
    running = game_running()
    if running:
        raise SaveError('Close Dune: Awakening before restoring a backup.')
    origin = Path((backup_dir / 'ORIGIN.txt').read_text(encoding='utf-8'))
    saved = backup_dir / origin.name
    if not saved.exists():
        raise SaveError('backup folder is missing its save files')
    for item in saved.rglob('*'):
        if item.is_file():
            target = origin / item.relative_to(saved)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
