"""Regressions for the 2026-11-26 verification defects (offline, temp dirs only)."""
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
import pytest
from test_r6_workspace import ctx, run, event, ROOT


def guard(ctx, command):
    return run('evidence_guard.mjs', event(ctx, {'command': command}, 'exec_command'), 'pre-tool-use')


@pytest.mark.parametrize('command', [
    'rm ev*/chat.txt',
    'rm -f e?idence/chat.txt',
    'node -e "require(\'fs\').unlinkSync(\'evid\'+\'ence/chat.txt\')"',
    'python3 -c "import os; os.remove(\'evid\'+\'ence/chat.txt\')"',
    'ffmpeg -i in.mp4 -y evidence/a.mp4 out.wav',
    'ffmpeg -loglevel error -i in.mp4 -y evidence/a.mp4 out.wav',
])
def test_guard_denies_glob_inline_and_ffmpeg_middle_output(ctx, command):
    (ctx/'evidence').mkdir(); (ctx/'evidence'/'chat.txt').write_text('x'); (ctx/'evidence'/'a.mp4').write_text('x')
    r = guard(ctx, command)
    assert r.returncode == 1, (command, r.stdout, r.stderr)
    assert '"deny"' in r.stdout


@pytest.mark.parametrize('command', [
    'rm *.log', 'rm -rf reports/*', 'python3 -c "import json; print(1)"',
    'ffmpeg -i evidence/a.mp4 -t 0.5 clip.wav', 'cat evidence/chat.txt',
])
def test_guard_still_allows_unrelated_globs_and_reads(ctx, command):
    (ctx/'evidence').mkdir(); (ctx/'evidence'/'chat.txt').write_text('x'); (ctx/'evidence'/'a.mp4').write_text('x')
    r = guard(ctx, command)
    assert r.returncode == 0, (command, r.stdout, r.stderr)


PY = sys.executable


def test_manifest_refuses_output_hard_linked_to_evidence(tmp_path):
    ev = tmp_path/'evidence'; ev.mkdir(); (ev/'a.txt').write_text('ORIGINAL')
    os.link(ev/'a.txt', tmp_path/'out.json')
    r = subprocess.run([PY, str(ROOT/'scripts/evidence_manifest.py'), 'evidence', '-o', 'out.json'], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode != 0, r.stdout
    assert (ev/'a.txt').read_text() == 'ORIGINAL'


def test_atomic_write_does_not_write_through_hard_link(tmp_path):
    sys.path.insert(0, str(ROOT/'scripts'))
    from evidence_output import atomic_write
    (tmp_path/'keep').write_text('KEEP'); os.link(tmp_path/'keep', tmp_path/'link')
    atomic_write(tmp_path/'link', b'new')
    assert (tmp_path/'keep').read_text() == 'KEEP' and (tmp_path/'link').read_text() == 'new'


@pytest.mark.parametrize('flags', [
    ['--output', '{src}'],
    ['--output', '{tmp}/out.txt', '--report', '{src}'],
    ['--output', '{tmp}/out.txt', '--vault', '{src}'],
    ['--output', '{tmp}/link.txt'],
    ['--output', '{tmp}/out.txt', '--report', '{tmp}/out.txt'],
])
def test_mask_pii_refuses_overlapping_paths(tmp_path, flags):
    src = tmp_path/'src.txt'; src.write_text('연락처 010-1234-5678\n', encoding='utf-8')
    os.link(src, tmp_path/'link.txt')
    args = [f.format(src=src, tmp=tmp_path) for f in flags]
    r = subprocess.run([PY, str(ROOT/'scripts/mask_korean_pii.py'), str(src), *args], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 2, r.stdout + r.stderr
    assert '1234-5678' in src.read_text(encoding='utf-8')


def test_mask_pii_distinct_paths_still_work(tmp_path):
    src = tmp_path/'src.txt'; src.write_text('연락처 010-1234-5678\n', encoding='utf-8')
    r = subprocess.run([PY, str(ROOT/'scripts/mask_korean_pii.py'), str(src), '--output', str(tmp_path/'out.txt'), '--report', str(tmp_path/'r.md')], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert '1234-5678' not in (tmp_path/'out.txt').read_text(encoding='utf-8')


def test_pii_vault_is_owner_only(tmp_path):
    src = tmp_path/'src.txt'; src.write_text('연락처 010-1234-5678\n', encoding='utf-8')
    vault = tmp_path/'v.pii-vault.json'
    old = os.umask(0o022)
    try:
        r = subprocess.run([PY, str(ROOT/'scripts/mask_korean_pii.py'), str(src), '--output', str(tmp_path/'out.txt'), '--vault', str(vault)], cwd=tmp_path, capture_output=True, text=True)
    finally:
        os.umask(old)
    assert r.returncode == 0, r.stderr
    if os.name != 'nt':
        assert stat.S_IMODE(vault.stat().st_mode) == 0o600
    assert json.loads(vault.read_text(encoding='utf-8'))['token_to_value']
