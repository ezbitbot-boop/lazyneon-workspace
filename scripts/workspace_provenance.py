"""Read-only identity of this installed workspace, never the evidence CWD."""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def workspace_provenance(root=ROOT):
    root = Path(root)
    def git(*args):
        try:
            p = subprocess.run(['git', '--no-optional-locks', '-C', str(root), *args], capture_output=True, text=True, timeout=2)
            return p.stdout.strip() if p.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None
    try:
        version = json.loads((root/'package.json').read_text())['version']
    except (OSError, ValueError, KeyError):
        version = 'unknown'
    # Avoid borrowing a containing repository's identity for an unpacked release.
    top = git('rev-parse', '--show-toplevel')
    valid = top is not None and os.path.realpath(top) == os.path.realpath(root)
    commit = git('rev-parse', 'HEAD') if valid else None
    status = git('status', '--porcelain', '--untracked-files=normal') if valid else None
    return {'workspace_version': version, 'git_commit': commit or 'unknown',
            'git_dirty': bool(status) if status is not None else 'unknown'}

def provenance_text():
    return 'Workspace provenance: ' + json.dumps(workspace_provenance(), ensure_ascii=False)

if __name__ == '__main__':
    print(json.dumps(workspace_provenance()))
