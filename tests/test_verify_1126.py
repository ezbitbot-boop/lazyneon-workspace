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


def _case_root(ev):
    module = (ROOT/'scripts'/'case_mode.mjs').as_uri()
    js = ("import {collectEvidenceFiles,hashEvidence,evidenceRootHash} from " + json.dumps(module)
          + "; const p=process.argv[1]; console.log(evidenceRootHash(await hashEvidence(collectEvidenceFiles(p)),p,true));")
    return subprocess.run(['node', '--input-type=module', '-e', js, str(ev)], capture_output=True, text=True, check=True).stdout.strip()


def test_report_verify_rejects_evidence_added_after_intake(tmp_path):
    sys.path.insert(0, str(ROOT/'scripts'))
    import hashlib
    from report_core import verified_evidence_text
    ev = tmp_path/'evidence'; ev.mkdir(); (ev/'a.txt').write_text('A')
    base = _case_root(ev)
    # Nested: a custody/ directly under tmp_path is visible to sibling tests' registries().
    (tmp_path/'w'/'custody').mkdir(parents=True); m = tmp_path/'w'/'custody'/'hashes-start.json'
    m.write_text(json.dumps({'tool': 'case_mode.mjs init', 'evidencePath': str(ev), 'rootHash': base,
                             'files': [{'path': str(ev/'a.txt'), 'sha256': hashlib.sha256(b'A').hexdigest(), 'sizeBytes': 1}]}))
    assert json.loads(verified_evidence_text(m))[-1] == {'rootHash': base}
    (ev/'planted.txt').write_text('added after intake')
    with pytest.raises(ValueError, match='baseline rootHash'):
        verified_evidence_text(m)


def _legacy_case(tmp_path, log_lines):
    import hashlib
    ev = tmp_path/'evidence'; ev.mkdir(); (ev/'a.txt').write_text('A')
    work = tmp_path/'case'; (work/'custody').mkdir(parents=True)
    (work/'custody'/'hashes-start.json').write_text(json.dumps({'tool': 'case_mode.mjs init', 'evidencePath': str(ev), 'timestamp': 'x',
        'files': [{'path': str(ev/'a.txt'), 'type': 'file', 'sha256': hashlib.sha256(b'A').hexdigest(), 'sizeBytes': 1}]}))
    if log_lines is not None:
        (work/'custody'/'log.jsonl').write_text(''.join(json.dumps(l)+'\n' for l in log_lines))
    return ev, work


@pytest.mark.parametrize('log', [None, [], [{'type': 'close', 'status': 'ok'}], [{'type': 'init', 'evidencePath': '/elsewhere'}]])
def test_case_close_requires_intake_record(tmp_path, log):
    ev, work = _legacy_case(tmp_path, log)
    r = subprocess.run(['node', str(ROOT/'scripts/case_mode.mjs'), 'close', '--case', str(work)], capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert 'CUSTODY INCOMPLETE' in r.stderr
    last = json.loads((work/'custody'/'log.jsonl').read_text().splitlines()[-1])
    assert last['type'] == 'close' and last['status'] == 'INTEGRITY_FAIL' and last['custodyProblems']


def test_case_close_ok_with_matching_intake_record(tmp_path):
    ev, work = _legacy_case(tmp_path, [])
    (work/'custody'/'log.jsonl').write_text(json.dumps({'type': 'init', 'evidencePath': str(ev)})+'\n')
    r = subprocess.run(['node', str(ROOT/'scripts/case_mode.mjs'), 'close', '--case', str(work)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def _unlock(record):
    return subprocess.run([PY, str(ROOT/'scripts'/'evidence_protection.py')], input=json.dumps({'action': 'unlock', 'record': record}),
                          capture_output=True, text=True, cwd=str(ROOT/'scripts'))


@pytest.mark.parametrize('change', ['replaced', 'missing'])
def test_unlock_checks_identity_before_changing_anything(tmp_path, change):
    a, b = tmp_path/'a.txt', tmp_path/'b.txt'
    entries = []
    for f in (a, b):
        f.write_text('orig'); os.chmod(f, 0o644); s = f.lstat()
        entries.append({'path': str(f), 'mode': 0o644, 'dev': s.st_dev, 'ino': s.st_ino, 'original_flags': 0, 'applied': ['chmod a-w'], 'status': 'protected'})
        os.chmod(f, 0o444)
    a.unlink()
    if change == 'replaced':
        a.write_text('replacement'); os.chmod(a, 0o600)
    r = _unlock({'platform': sys.platform, 'entries': entries, 'notes': []})
    assert r.returncode == 2, r.stdout + r.stderr
    assert '복구 불완전' in r.stderr
    if change == 'replaced':
        assert stat.S_IMODE(a.lstat().st_mode) == 0o600
    assert stat.S_IMODE(b.lstat().st_mode) == 0o444  # nothing changed when any entry fails


def test_unlock_restores_matching_entries(tmp_path):
    f = tmp_path/'a.txt'; f.write_text('orig'); os.chmod(f, 0o644); s = f.lstat(); os.chmod(f, 0o444)
    r = _unlock({'platform': sys.platform, 'entries': [{'path': str(f), 'mode': 0o644, 'dev': s.st_dev, 'ino': s.st_ino, 'original_flags': 0, 'applied': ['chmod a-w'], 'status': 'protected'}], 'notes': []})
    assert r.returncode == 0, r.stderr
    assert stat.S_IMODE(f.lstat().st_mode) == 0o644


@pytest.mark.parametrize('kind', ['file', 'dir'])
def test_manifest_refuses_symlinks_in_evidence(tmp_path, kind):
    ev = tmp_path/'evidence'; ev.mkdir(); (ev/'a.txt').write_text('a')
    (tmp_path/'outside').mkdir(); (tmp_path/'outside'/'secret.txt').write_text('outside')
    target = '../outside/secret.txt' if kind == 'file' else '../outside'
    os.symlink(target, ev/'link')
    r = subprocess.run([PY, str(ROOT/'scripts/evidence_manifest.py'), 'evidence', '-o', 'm.json'], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 2, r.stdout + r.stderr
    assert 'link' in r.stderr and not (tmp_path/'m.json').exists()


def test_manifest_generate_then_verify_round_trip(tmp_path):
    ev = tmp_path/'evidence'; (ev/'sub').mkdir(parents=True); (ev/'a.txt').write_text('a'); (ev/'sub'/'b.txt').write_text('b')
    gen = subprocess.run([PY, str(ROOT/'scripts/evidence_manifest.py'), 'evidence', '-o', 'm.json'], cwd=tmp_path, capture_output=True, text=True)
    assert gen.returncode == 0, gen.stderr
    assert sorted(f['path'] for f in json.loads((tmp_path/'m.json').read_text())['files']) == ['a.txt', os.path.join('sub', 'b.txt')]
    ver = subprocess.run([PY, str(ROOT/'scripts/evidence_manifest.py'), 'evidence', '--verify', 'm.json'], cwd=tmp_path, capture_output=True, text=True)
    assert ver.returncode == 0, ver.stdout + ver.stderr
