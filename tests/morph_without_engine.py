"""Run a verifier with stdlib only, retaining the caller's environment.

Invoke with Python -S. Unlike -S alone, remove PYTHONPATH entries too so
optional packages installed there cannot turn absence tests into presence tests.
No replacement engine is installed; verify actual import unavailability first.
"""
import importlib.util
import os
from pathlib import Path
import runpy
import sys

extra_paths = {str(Path(p).resolve()) for p in os.environ.get('PYTHONPATH', '').split(os.pathsep) if p}
sys.path[:] = [p for p in sys.path if str(Path(p).resolve()) not in extra_paths]
assert importlib.util.find_spec('kiwipiepy') is None, 'absence test can still import Kiwi'
sys.argv = sys.argv[1:]
sys.path.insert(0, str(Path(sys.argv[0]).resolve().parent))
runpy.run_path(sys.argv[0], run_name='__main__')
