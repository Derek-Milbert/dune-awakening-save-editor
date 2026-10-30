"""Launch the Dune: Awakening Save Editor.   python run.py [--port 8765] [--no-browser] [--save-root FOLDER]"""
import argparse
import os
import sys

if sys.version_info < (3, 10):
    raise SystemExit('Python 3.10 or newer is required (you have %d.%d).' % sys.version_info[:2])

from dune_editor.server import serve

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=8765, help='first port to try (default 8765; the next 19 are tried if it is busy)')
    ap.add_argument('--no-browser', action='store_true', help="don't open the browser automatically")
    ap.add_argument('--save-root', metavar='FOLDER', help='folder to search for saves instead of '
                    '%%LOCALAPPDATA%%\\DuneSandbox\\Saved\\Cloud\\PlayerClientStorage (it must contain <environment>\\<account id>\\game.db)')
    a = ap.parse_args()
    if a.save_root:
        os.environ['DUNE_EDITOR_SAVE_ROOT'] = a.save_root
    serve(a.port, not a.no_browser)
