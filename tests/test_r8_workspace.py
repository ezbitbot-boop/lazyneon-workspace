"""R8 regressions: real guard process and stubbed STT process boundary; no network."""
import json
import subprocess
from pathlib import Path

import pytest
from test_r3_workspace import load, ROOT


def guard(tmp_path, args, name='write_to_file'):
    return subprocess.run(['node', str(ROOT/'scripts/evidence_guard.mjs'), 'pre-tool-use'],
        input=json.dumps({'workspacePaths': [str(tmp_path)], 'toolCall': {'name': name, 'args': args}}),
        text=True, capture_output=True, timeout=10)


@pytest.mark.parametrize('script', ['classify-task.mjs', 'report-tools.mjs'])
@pytest.mark.parametrize('kind', ['missing', 'attacker', 'symlink'])
def test_untrusted_readonly_script_names(tmp_path, script, kind):
    target = tmp_path/script
    if kind == 'attacker':
        target.write_text('throw new Error("must never execute")')
    elif kind == 'symlink':
        evil = tmp_path/'evil'; evil.write_text('throw new Error("must never execute")')
        target.symlink_to(evil)
    result = guard(tmp_path, {'CommandLine': f'node "{target}" claims gate evidence/disk.raw'}, 'run_command')
    assert result.returncode == 1, result.stdout


@pytest.mark.parametrize('name', ['REPORT.TXT', 'disk.raw.txt', 'disk.rаw', 'renamed'])
@pytest.mark.parametrize('protection', ['root', 'manifest', 'signature', 'symlink'])
def test_renamed_evidence_protected(tmp_path, name, protection):
    target = tmp_path/name
    if protection == 'root':
        root = tmp_path/'originals'; root.mkdir()
        (tmp_path/'manifest.json').write_text(json.dumps({'manifest_version': 1, 'root': str(root), 'files': []}))
        target = root/name
        target.write_bytes(b'opaque bytes')
    elif protection == 'manifest':
        target.write_bytes(b'opaque bytes')
        (tmp_path/'manifest.json').write_text(json.dumps({'schema_version': 'lazy-evidence-case-v1', 'items': [{'source': {'path': name}}]}))
    elif protection == 'signature':
        original = tmp_path/'original.evtx'; original.write_bytes(b'ElfFile\x00'+b'\x00'*64)
        original.rename(target)
    else:
        root = tmp_path/'evidence'; root.mkdir()
        original = root/'opaque'; original.write_bytes(b'opaque bytes')
        target.symlink_to(original)
    assert guard(tmp_path, {'TargetFile': str(target)}).returncode == 1
    assert guard(tmp_path, {'CommandLine': f'rm "{target}"'}, 'run_command').returncode == 1
    assert guard(tmp_path, {'CommandLine': f'sha256sum "{target}"'}, 'run_command').returncode == 0


def test_symlink_directory_and_spaces(tmp_path):
    root = tmp_path/'evidence'; root.mkdir()
    alias = tmp_path/'alias'; alias.symlink_to(root, target_is_directory=True)
    assert guard(tmp_path, {'TargetFile': str(alias/'new name.txt')}).returncode == 1
    target = tmp_path/'space name.txt'; target.write_bytes(b'ElfFile\x00')
    assert guard(tmp_path, {'TargetFile': str(target)}).returncode == 1
    assert guard(tmp_path, {'CommandLine': f'rm "{target}"'}, 'run_command').returncode == 1


@pytest.mark.parametrize('engine', ['faster-whisper', 'sensevoice', 'youtube-subs'])
@pytest.mark.parametrize('url', ['https://www.youtube.com/watch?v=abcdefghijk', 'https://example.invalid/?youtube.com'])
def test_url_requires_upload_consent(tmp_path, monkeypatch, engine, url):
    stt = load('scripts/local_stt.py')
    calls = []
    monkeypatch.setattr(stt, '_engine_available', lambda _: True)
    monkeypatch.setattr(stt.shutil, 'which', lambda _: '/stub/yt-dlp')
    monkeypatch.setattr(stt.subprocess, 'run', lambda *a, **k: calls.append(a))
    assert stt.main([url, '--engine', engine]) == 2
    assert calls == []


@pytest.mark.parametrize('url', ['https://youtube.com.evil.invalid/watch?v=abcdefghijk', 'https://example.invalid/?youtube.com', 'https://youtube.com@evil.invalid/watch?v=abcdefghijk'])
def test_youtube_hostname_not_substring(monkeypatch, url):
    stt = load('scripts/local_stt.py')
    assert stt._extract_youtube_url(url) is None


def test_youtube_offline_and_direct_consent(monkeypatch):
    monkeypatch.delenv('LAZYNEON_OFFLINE', raising=False)
    stt = load('scripts/local_stt.py')
    calls = []
    monkeypatch.setattr(stt.shutil, 'which', lambda _: '/stub/yt-dlp')
    monkeypatch.setattr(stt.subprocess, 'run', lambda *a, **k: calls.append(a))
    with pytest.raises(PermissionError, match='--upload-audio'):
        stt.transcribe_youtube_subs('https://youtu.be/abcdefghijk')
    monkeypatch.setenv('LAZYNEON_OFFLINE', '1')
    with pytest.raises(PermissionError, match='OFFLINE'):
        stt.transcribe_youtube_subs('https://youtu.be/abcdefghijk', allow_upload=True)
    assert stt.main(['https://youtu.be/abcdefghijk', '--engine', 'faster-whisper', '--upload-audio']) == 2
    assert calls == []


def test_consented_url_stub_only(tmp_path, monkeypatch):
    stt = load('scripts/local_stt.py')
    monkeypatch.delenv('LAZYNEON_OFFLINE', raising=False)
    monkeypatch.setattr(stt, '_engine_available', lambda _: True)
    monkeypatch.setattr(stt.shutil, 'which', lambda _: '/stub/yt-dlp')
    calls = []
    def run(cmd, **kwargs):
        calls.append(cmd)
        Path(cmd[cmd.index('-o')+1]).parent.joinpath('sub.ko.vtt').write_text('WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello\n')
    monkeypatch.setattr(stt.subprocess, 'run', run)
    assert stt.main(['https://youtu.be/abcdefghijk', '--engine', 'faster-whisper', '--upload-audio']) == 0
    assert len(calls) == 1


def test_case_mode_evidence_root(tmp_path):
    root = tmp_path/'originals'; root.mkdir()
    source = root/'source'; source.write_bytes(b'opaque')
    case = tmp_path/'case'
    result = subprocess.run(['node', str(ROOT/'scripts/case_mode.mjs'), 'init', str(root), '--out', str(case)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    # OS protection now prevents rename until an explicit logged unlock.
    with pytest.raises(PermissionError): source.rename(root/'renamed.txt')
    unlocked = subprocess.run(['node', str(ROOT/'scripts/case_mode.mjs'), 'unlock', '--case', str(case), '--reason', 'test rename identity'], capture_output=True, text=True)
    assert unlocked.returncode == 0, unlocked.stderr
    renamed = root/'renamed.txt'; source.rename(renamed)
    assert guard(case, {'TargetFile': str(renamed)}).returncode == 1
