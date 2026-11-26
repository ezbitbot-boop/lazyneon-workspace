"""Always release OS protection on pytest-owned temporary trees."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

def release_tree(root):
    """Remove every OS protection from a test-owned tree so it can be changed and deleted."""
    root = Path(root)
    # Parametrized binary payload IDs can exceed execve's environment limit.
    cleanup_env = {k: v for k, v in os.environ.items() if k != 'PYTEST_CURRENT_TEST'}
    if sys.platform == 'darwin':
        subprocess.run(['chflags','-R','nouchg',str(root)],check=True, env=cleanup_env)
    user = subprocess.check_output(['whoami'],text=True, env=cleanup_env).strip() if os.name=='nt' else None
    for p in [root,*root.rglob('*')]:
        if p.is_symlink(): continue
        if sys.platform.startswith('linux') and shutil.which('chattr'):
            subprocess.run(['chattr','-i',str(p)],capture_output=True, env=cleanup_env)
        if os.name=='nt':
            # The deny ACE also denies changing attributes, so it goes first.
            subprocess.run(['icacls',str(p),'/remove:d',user],capture_output=True, env=cleanup_env)
            subprocess.run(['attrib','-R',str(p)],capture_output=True, env=cleanup_env)
        p.chmod(p.stat().st_mode|0o700)


@pytest.fixture(autouse=True)
def release_test_evidence(tmp_path):
    try:
        yield
    finally:
        # tmp_path is created by pytest for this test, never a user evidence root.
        release_tree(tmp_path)
