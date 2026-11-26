"""Windows evidence protection: deny ACE + read-only attribute, verified on a real NTFS volume."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import evidence_protection as ep

USER = r'host\user'
ICACLS = r'''C:\case\증거\a.txt {ace}
                     NT AUTHORITY\SYSTEM:(I)(F)
                     BUILTIN\Administrators:(I)(F)

Successfully processed 1 files; Failed processing 0 files
'''


@pytest.mark.parametrize('ace, present', [
    (r'HOST\User:(DENY)(DE,WD,AD,WEA,DC,WA)', True),  # icacls's own order and case
    (r'host\user:(DENY)(WD,AD,WEA,WA,DE,DC)', True),
    (r'host\user:(DENY)(W,D,DC)', False),             # simple rights also deny reading
    (r'host\user:(DENY)(WD)', False),                 # allows del /f, attrib -R, moving out
    (r'host\user:(DENY)(DE,WD,AD,WEA,DC,WA,RD)', False),
    (r'host\user:(I)(DENY)(DE,WD,AD,WEA,DC,WA)', False),  # inherited, not our ACE
    (r'host\user:(DE,WD,AD,WEA,DC,WA)', False),       # allow, not deny
    (r'other\user:(DENY)(DE,WD,AD,WEA,DC,WA)', False),
    (r'xhost\user:(DENY)(DE,WD,AD,WEA,DC,WA)', False),
    (r'host\user:(F)', False),
])
def test_acl_present_requires_exact_deny_set(monkeypatch, ace, present):
    monkeypatch.setattr(ep, 'checked', lambda *a: ICACLS.format(ace=ace))
    assert ep.acl_present({'path': r'C:\case\증거\a.txt', 'user': USER}) is present


def _run(*args):
    return subprocess.run(args, capture_output=True, text=True)


def _snapshot(paths):
    return {p: (_run('icacls', str(p)).stdout, p.stat().st_file_attributes) for p in paths}


@pytest.mark.skipif(os.name != 'nt', reason='icacls deny ACEs and the read-only attribute exist only on Windows')
def test_windows_protect_denies_changes_allows_reads_and_unlock_restores(tmp_path, monkeypatch):
    # pytest makes tmp_path with mode 0o700: a DACL without auto-inheritance, so the ACEs its
    # children inherit are not marked inherited, and any icacls change on a child adds them a
    # second time as inherited. Give the case folder the ordinary inherited DACL of a user folder.
    root = tmp_path/'case'; root.mkdir()
    assert _run('icacls', str(root), '/reset').returncode == 0
    monkeypatch.chdir(root)  # protect() consults lock records under cwd
    ev = root/'증거 folder'; sub = ev/'sub'; sub.mkdir(parents=True)
    f, g = ev/'a.txt', sub/'b.txt'
    f.write_text('orig'); g.write_text('nested')
    other = root/'other'; other.mkdir()
    before = _snapshot([ev, sub, f, g])
    user = _run('whoami').stdout.strip()

    record = ep.protect([ev])
    try:
        assert all(e['status'] == 'protected' and {'attrib +R', 'deny-write ACL'} <= set(e['applied'])
                   for e in record['entries']), record
        assert ep.verify(record) == []

        # Reading, listing and hashing keep working, from Python and from Node (case-mode).
        assert f.read_text() == 'orig' and g.read_text() == 'nested'
        assert sorted(os.listdir(ev)) == ['a.txt', 'sub'] and os.listdir(sub) == ['b.txt']
        node = _run('node', '-e', "const fs=require('fs'),d=process.argv[1];"
                    "console.log(fs.readdirSync(d).join(','),fs.readFileSync(d+'/sub/b.txt','utf8'))", str(ev))
        assert node.returncode == 0 and node.stdout.split() == ['a.txt,sub', 'nested'], node.stderr

        denied = {
            'write': lambda: f.open('r+b'),
            'append': lambda: f.open('ab'),
            'truncate': lambda: f.open('wb'),
            'create file': lambda: (ev/'new.txt').write_text('n'),
            'create nested file': lambda: (sub/'new.txt').write_text('n'),
            'mkdir': lambda: (ev/'newdir').mkdir(),
            'delete': lambda: os.remove(f),
            'delete nested': lambda: os.remove(g),
            'rename': lambda: os.rename(f, ev/'renamed.txt'),
            'move file out': lambda: os.rename(g, other/'moved.txt'),
            'move folder out': lambda: os.rename(sub, other/'moved'),
            'remove folder': lambda: shutil.rmtree(sub),
            'clear read-only': lambda: os.chmod(f, 0o666),
        }
        for name, op in denied.items():
            with pytest.raises(PermissionError):
                op()
                pytest.fail(f'{name} was allowed')
        # Shell tools that clear the read-only attribute themselves.
        _run('attrib', '-R', str(f))
        _run('cmd', '/c', 'del', '/f', '/q', str(f))
        _run('powershell', '-NoProfile', '-Command', f"Remove-Item -Force -Recurse -LiteralPath '{ev}'")
        assert f.read_text() == 'orig' and g.read_text() == 'nested'
        assert sorted(os.listdir(ev)) == ['a.txt', 'sub'] and os.listdir(sub) == ['b.txt'] and not os.listdir(other)
        assert ep.verify(record) == []

        # Verification fails closed when either half of the protection is gone.
        assert _run('icacls', str(g), '/remove:d', user).returncode == 0
        assert ep.verify(record) == [f'PROTECTION deny-write ACL missing: {g}']
        assert _run('attrib', '-R', str(g)).returncode == 0
        assert ep.verify(record) == [f'PROTECTION read-only attribute missing: {g}',
                                     f'PROTECTION deny-write ACL missing: {g}']
    finally:
        ep.unlock(record)

    assert _snapshot([ev, sub, f, g]) == before
    f.write_text('changed'); (ev/'new.txt').write_text('n'); os.rename(g, other/'moved.txt'); shutil.rmtree(ev)
