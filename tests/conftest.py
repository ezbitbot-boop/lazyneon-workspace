"""Always release OS protection on pytest-owned temporary trees."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

@pytest.fixture(autouse=True)
def release_test_evidence(tmp_path):
    try:
        yield
    finally:
        # tmp_path is created by pytest for this test, never a user evidence root.
        # Parametrized binary payload IDs can exceed execve's environment limit.
        cleanup_env = {k: v for k, v in os.environ.items() if k != 'PYTEST_CURRENT_TEST'}
        if sys.platform == 'darwin':
            subprocess.run(['chflags','-R','nouchg',str(tmp_path)],check=True, env=cleanup_env)
        for p in [tmp_path,*tmp_path.rglob('*')]:
            if p.is_symlink(): continue
            if sys.platform.startswith('linux') and shutil.which('chattr'):
                subprocess.run(['chattr','-i',str(p)],capture_output=True, env=cleanup_env)
            if os.name=='nt':
                user=subprocess.check_output(['whoami'],text=True, env=cleanup_env).strip()
                subprocess.run(['icacls',str(p),'/remove:d',user],capture_output=True, env=cleanup_env)
                subprocess.run(['attrib','-R',str(p)],capture_output=True, env=cleanup_env)
            p.chmod(p.stat().st_mode|0o700)
