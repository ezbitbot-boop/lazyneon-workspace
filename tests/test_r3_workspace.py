"""Offline regressions for fresh-install review; never contacts STT providers."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import types
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

def load(rel):
    spec = importlib.util.spec_from_file_location('r3_' + Path(rel).stem, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def hook(name, payload, cwd, env=None):
    return subprocess.run(['node', str(ROOT / 'scripts' / (name + '.mjs')),
                           *(['post-tool-use'] if name == 'evidence_guard' else [])],
                          input=json.dumps(payload), text=True, capture_output=True, cwd=cwd,
                          env={**os.environ, **(env or {})}, timeout=10)

def test_all_audio_entrypoints_require_consent(monkeypatch, tmp_path):
    stt = load('scripts/local_stt.py')
    video = load('skills/forensic-video/scripts/whisper.py')
    calls = []
    class Recognizer:
        def recognize_google(self, *args, **kwargs):
            calls.append('google')
            return 'stub'
    monkeypatch.setitem(sys.modules, 'speech_recognition', types.SimpleNamespace(
        Recognizer=Recognizer, AudioData=lambda *a: a))
    monkeypatch.setattr(stt, '_probe_duration', lambda _: 1)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: types.SimpleNamespace(stdout=b'0' * 32000))
    monkeypatch.setattr(subprocess, 'check_output', lambda *a, **k: '1')
    operations = [lambda: stt.transcribe_google_server(tmp_path / 'audio.wav'),
                  lambda: stt.transcribe_file(tmp_path / 'audio.wav', 'google-server', 'ko', False, 'tiny'),
                  lambda: video._transcribe_google_server('audio.wav'),
                  lambda: video._transcribe_groq(tmp_path / 'audio.wav', 'fake'),
                  lambda: video._transcribe_openai(tmp_path / 'audio.wav', 'fake')]
    for operation in operations:
        with pytest.raises(PermissionError, match='--upload-audio'):
            operation()
    assert calls == []
    stt.transcribe_google_server(tmp_path / 'audio.wav', allow_upload=True)
    video._transcribe_google_server('audio.wav', allow_upload=True)
    assert calls == ['google', 'google']

def test_survey_consent_and_engine_selection(monkeypatch, tmp_path):
    stt = load('scripts/local_stt.py')
    monkeypatch.setattr(stt.importlib.util, 'find_spec', lambda n: object() if n == 'speech_recognition' else None)
    monkeypatch.setattr(stt.shutil, 'which', lambda n: '/fake/ffmpeg' if n == 'ffmpeg' else None)
    assert stt.detect_engine() is None
    assert stt.detect_engine(allow_upload=True) == 'google-server'
    survey = load('scripts/case_survey.py')
    original = survey._load
    monkeypatch.setattr(survey, '_load', lambda n: stt if n == 'local_stt' else original(n))
    report = survey.survey(tmp_path, [], True)
    assert '동의' in json.dumps(report['steps']['stt'], ensure_ascii=False)
    assert '--upload-audio' in subprocess.run([sys.executable, str(ROOT/'scripts/case_survey.py'), '--help'], capture_output=True, text=True).stdout

def test_workspace_payload_pins_and_case_audit(tmp_path):
    case = tmp_path / 'case'; case.mkdir()
    (case / '.lazyneon').mkdir()
    (case / '.lazyneon/pins.md').write_text('PIN-R3-CASE')
    payload = {'workspacePaths': [str(case)], 'cwd': str(tmp_path)}
    assert 'PIN-R3-CASE' not in hook('session_start', payload, ROOT).stdout
    source = case / 'source.txt'; source.write_text('evidence')
    payload['toolCall'] = {'name': 'write_to_file', 'args': {'TargetFile': 'source.txt'}}
    assert hook('evidence_guard', payload, tmp_path).returncode == 0
    audit = case / '.lazyneon-workspace/audit_trail.jsonl'
    assert audit.exists()
    assert not (tmp_path / '.lazyneon-workspace').exists()
    (case/'sources').mkdir()
    (case/'sources/source.txt').write_bytes(source.read_bytes())
    report = case / '감정보고서.md'
    import hashlib
    report.write_text('# 감정 보고서\n## 해시 검증\nsource.txt SHA-256: ' + hashlib.sha256(b'evidence').hexdigest())
    payload['toolCall']['args']['TargetFile'] = str(report)
    result = hook('hallucination_guard', payload, tmp_path, {'LAZYNEON_WS_PYTHON': sys.executable})
    assert '근거 없는 해시' not in result.stderr
    assert '--evidence 미제시' not in result.stderr
    direct = subprocess.run([sys.executable, str(ROOT/'scripts/verify_report.py'), str(report), '--evidence', str(audit), '--require-sources', '--sources', str(case/'sources'), '--json'], capture_output=True, text=True)
    assert direct.returncode == 0, direct.stdout
    assert json.loads(direct.stdout)['verdict'] in ('PASS', 'WARN')
    from korean_morph_forensic import get_kiwi_instance
    if get_kiwi_instance() is None:
        assert result.returncode == 1
        assert 'kiwipiepy 엔진 사용 불가' in result.stderr
        assert json.loads(result.stdout)['decision'] == 'block'
    else:
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {'status': 'PASS'}
    report.write_text(report.read_text().replace(hashlib.sha256(b'evidence').hexdigest(), 'f' * 64))
    result = hook('hallucination_guard', payload, tmp_path, {'LAZYNEON_WS_PYTHON': sys.executable})
    assert result.returncode == 1, result.stderr
    assert '근거 없는 해시' in result.stderr
    assert json.loads(result.stdout)['decision'] == 'block'
    relay_env = {**os.environ, 'HOME': str(tmp_path), 'LAZYNEON_WS_PYTHON': sys.executable}
    for action in ('batch', 'inject'):
        relay = subprocess.run(['node', str(ROOT/'scripts/domain_feedback.mjs'), action, *(['hallucination_guard.mjs'] if action == 'batch' else [])], input=json.dumps(payload), text=True, capture_output=True, env=relay_env, timeout=30)
        assert relay.returncode == 0, relay.stderr
    message = json.loads(relay.stdout)['injectSteps'][0]['ephemeralMessage']
    # A forged hash is a definite failure even when morphology is unavailable.
    assert 'FAIL' in message
    records = [json.loads(line) for p in (tmp_path/'.lazyneon-workspace/feedback').glob('*.jsonl') for line in p.read_text().splitlines()]
    assert records[-1]['kind'] == 'fail'

def test_windows_eol_and_exit_code_contract():
    files = ['bin/lazyforensic', 'bin/lazyothers', 'bin/case-mode']
    r = subprocess.run(['git', 'check-attr', 'eol', '--', *files], cwd=ROOT, capture_output=True, text=True, check=True)
    assert all(line.endswith(': lf') for line in r.stdout.splitlines())
    for name in ('lazyforensic', 'lazyothers'):
        text = (ROOT / f'bin/{name}.cmd').read_text()
        assert 'ExecutionPolicy Bypass' in text
        assert text.strip().endswith('exit /b %ERRORLEVEL%')
        assert '(' not in text

def test_setup_includes_parser_requirements():
    text = (ROOT/'scripts/setup_forensic_env.py').read_text()
    assert 'requirements.txt' in text and '"-r"' in text
    for name in ('lazyforensic', 'lazyothers'):
        assert 'Scripts/python.exe' in (ROOT/f'bin/{name}').read_text()

@pytest.mark.parametrize('guard,title', [('hallucination_guard', '감정 보고서 SHA-256'), ('legal_factuality_guard', '소장 청구원인')])
def test_guards_use_explicit_python_and_reject_clt_stub(tmp_path, guard, title):
    report = tmp_path / '감정보고서_소장.md'; report.write_text('# ' + title)
    fake = tmp_path / 'python-stub'
    fake.write_text('#!/bin/sh\necho "xcode-select: note: No developer tools were found" >&2\nexit 1\n'); fake.chmod(0o755)
    result = hook(guard, {'workspacePaths': [str(tmp_path)], 'toolCall': {'args': {'TargetFile': str(report)}}}, ROOT, {'LAZYNEON_WS_PYTHON': str(fake)})
    assert result.returncode != 0, result.stderr
    assert 'python 실행' in result.stderr
    assert 'NOT_CHECKED' in result.stderr
    assert json.loads(result.stdout)['decision'] == 'block'

def test_default_collection_is_lazy_and_marked():
    config = ROOT / 'pytest.ini'
    assert config.exists() and 'not kakao' in config.read_text()
    tree = ast.parse((ROOT/'test/test_forensic_scripts.py').read_text())
    assert not any(isinstance(n, ast.Assign) and 'parse_kakao' in ast.unparse(n) for n in tree.body)
    text = (ROOT/'test/test_review_regressions.py').read_text()
    assert '@pytest.mark.kakao' in text

def test_audit_detects_server_and_package_network(tmp_path):
    audit = load('scripts/local_only_audit.py')
    p = tmp_path/'network.py'
    for source in ['rec.recognize_google(audio)', 'import speech_recognition', 'subprocess.run(["npx", "-y", "pkg"])', 'npm exec pkg', 'pip install pkg', 'yt-dlp url']:
        p.write_text(source)
        assert audit.scan_file(p, tmp_path, set()), source
    assert '["npx", "-y", "@firecrawl/anydoc", file_path]' not in (ROOT/'scripts/parse_korean_doc.py').read_text()

def test_powershell_command_parity():
    sh = (ROOT/'bin/lazyforensic').read_text().split('case "$cmd" in')[1]
    ps = (ROOT/'bin/lazyforensic.ps1').read_text()
    commands = set(re.findall(r'^  ([a-z|]+)\)', sh, re.M))
    commands = {c for item in commands for c in item.split('|')}
    for command in commands:
        assert re.search(r'"' + command + r'"\s*\{', ps), command
    assert (ROOT/'bin/case-mode.ps1').exists()
    assert (ROOT/'bin/case-mode.cmd').exists()

def test_core_claim_gate_readonly_contract(tmp_path):
    base = 'node ~/.gemini/config/plugins/lazyneon/skills/ulw-research/scripts/report-tools.mjs claims '
    for command in [base + 'snapshot --session-dir research/s1 --from S3=case/evidence/판결문.txt', base + 'gate --session-dir research/s1', base + 'report --session-dir research/s1']:
        p = subprocess.run(['node', str(ROOT/'scripts/evidence_guard.mjs'), 'pre-tool-use'], input=json.dumps({'toolCall': {'name': 'run_command', 'args': {'CommandLine': command}}}), capture_output=True, text=True)
        # External core script names are not proof of read-only behavior.
        assert 'allow' in p.stdout, p.stdout  # r10: --from is a read input
    for command in ['node x.mjs --out case/evidence/new.txt', base + 'snapshot --session-dir case/evidence/out --from S3=src.txt', base + 'snapshot --out case/evidence/new.txt', base + 'snapshot --from S3=case/evidence/in.txt > case/evidence/out.txt']:
        p = subprocess.run(['node', str(ROOT/'scripts/evidence_guard.mjs'), 'pre-tool-use'], input=json.dumps({'toolCall': {'args': {'CommandLine': command}}}), capture_output=True, text=True)
        assert 'deny' in p.stdout

def test_video_dependency_skip_is_explicit():
    text = (ROOT/'tests/test_workspace_regressions.py').read_text()
    assert 'shutil.which("ffmpeg")' in text
    assert 'skipif' in text

def test_video_upload_consent_without_ffmpeg(monkeypatch, tmp_path):
    video = load('skills/forensic-video/scripts/whisper.py')
    monkeypatch.setattr(video.shutil, 'which', lambda _: None)
    assert video.transcribe_video('absent.mp4', tmp_path) == []
    with pytest.raises(PermissionError, match='--upload-audio'):
        video._transcribe_google_server('absent.mp4')

def test_bootstrap_current_name():
    text = (ROOT/'bootstrap.sh').read_text()
    assert 'lazyforensic.git' not in text
    assert 'cd lazyneon-workspace' in text
    assert 'https://github.com/ezbitbot-boop/lazyneon-workspace.git' in text

def test_session_timeout_and_context_limits(tmp_path):
    p = subprocess.Popen(['node', str(ROOT/'scripts/session_start.mjs')], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        p.wait(timeout=2.5)
        assert json.loads(p.stdout.read())['injectSteps']
    finally:
        if p.poll() is None: p.kill(); p.wait()
        p.stdin.close()
    (tmp_path/'.lazyneon').mkdir()
    (tmp_path/'.lazyneon/pins.md').write_text('\n'.join(f'PIN-{i}' for i in range(500)))
    out = hook('session_start', {'workspacePaths': [str(tmp_path)]}, ROOT).stdout
    assert 'PIN-499' not in out and 'PIN-479' not in out
    assert len(re.findall(r'PIN-\d+', out)) == 0

def test_windows_install_docs():
    for name in ['README.md', 'docs/USER_GUIDE.md']:
        text = (ROOT/name).read_text()
        assert 'ExecutionPolicy Bypass' in text
        assert 'npx' in text and '네트워크' in text
    for name in ['bootstrap.sh', 'bin/lazyforensic.ps1', 'bin/lazyothers.ps1', 'scripts/setup_forensic_env.ps1']:
        text = (ROOT/name).read_text()
        assert '3.10+' not in text and '3.11+' not in text

def test_setup_powershell_delegates_same_requirements():
    text = (ROOT/'scripts/setup_forensic_env.ps1').read_text()
    assert '& $python' in text and 'setup_forensic_env.py' in text
    assert '"--dir"' in text and '"--with"' in text
    assert '$pip install' not in text

def test_unrelated_collection_never_executes_parser():
    # A real audit hook fails before forbidden module bytecode can execute.
    code = '''
import runpy, sys
from pathlib import Path
def guard(event, args):
    if event == 'exec' and 'kakao' in args[0].co_filename.lower():
        raise AssertionError('forbidden parser execution during collection')
sys.addaudithook(guard)
runpy.run_path('test/test_forensic_scripts.py', run_name='collection_probe')
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

@pytest.mark.parametrize('guard', ['hallucination_guard', 'legal_factuality_guard'])
@pytest.mark.parametrize('verifier_result', ['success', 'empty', 'failed', 'nonzero'])
def test_guard_explicit_python_receives_workspace_evidence(tmp_path, guard, verifier_result):
    case = tmp_path/'case'; case.mkdir()
    report = case/'감정보고서_소장.md'; report.write_text('# 감정 보고서\n청구원인\nSHA-256 미측정')
    (case/'facts.txt').write_text('청구원인')
    (case/'claim-ledger.md').write_text('ledger')
    (case/'.lazyneon-workspace').mkdir()
    (case/'.lazyneon-workspace/audit_trail.jsonl').write_text('{}')
    (case/'audit.json').write_text('{}') # Untrusted sibling must not be adopted
    (case/'timeline.json').write_text('{"events": []}')
    # This recording interpreter tests delivery, not verification internals.
    # Exit zero plus {} is NOT a successful verifier result under fail-closed.
    verdict = 'FAIL' if verifier_result == 'failed' else 'PASS'
    output = (f'[{verdict}] report verification' if guard == 'hallucination_guard'
              else json.dumps({'verdict': verdict, 'errors': ['invalid evidence'] if verdict == 'FAIL' else []}))
    if verifier_result == 'empty':
        output = '{}'
    fake = tmp_path/'python'; log = tmp_path/'argv.json'
    fake.write_text('#!' + sys.executable + '\nimport json,sys\nfrom pathlib import Path\nPath(' + repr(str(log)) + ').write_text(json.dumps(sys.argv))\nprint(' + repr(output) + ')\nsys.exit(' + ('1' if verifier_result == 'nonzero' else '0') + ')\n')
    fake.chmod(0o755)
    result = hook(guard, {'workspacePaths': [str(case)], 'toolCall': {'args': {'TargetFile': report.name}}}, ROOT, {'LAZYNEON_WS_PYTHON': str(fake)})
    args = json.loads(log.read_text())
    assert str(report) in args and str(case/'claim-ledger.md') in args
    assert str(case/('.lazyneon-workspace/audit_trail.jsonl' if guard == 'hallucination_guard' else 'facts.txt')) in args
    assert args[1] == str(ROOT/'scripts'/('verify_report.py' if guard == 'hallucination_guard' else 'verify_legal_factuality.py'))
    assert args[args.index('--claim-ledger') + 1] == str(case/'claim-ledger.md')
    evidence_flag = '--evidence' if guard == 'hallucination_guard' else '--source'
    assert args[args.index(evidence_flag) + 1] == str(case/('.lazyneon-workspace/audit_trail.jsonl' if guard == 'hallucination_guard' else 'facts.txt'))
    if guard == 'hallucination_guard':
        assert str(case/'audit.json') not in args
        assert args[args.index('--timeline') + 1] == str(case/'timeline.json')
        assert 'timeline 근거 파일 미발견' not in result.stderr
    if verifier_result == 'success':
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {'status':'PASS'}
    else:
        assert result.returncode == 1, result.stderr
        assert json.loads(result.stdout)['decision'] == 'block'
        if verifier_result == 'empty':
            assert 'NOT_CHECKED' in result.stderr

def test_audit_isolated_between_cases_and_missing_workspace(tmp_path):
    for name in ['a', 'b']:
        case = tmp_path/name; case.mkdir()
        source = case/'source.txt'; source.write_text(name)
        result = hook('evidence_guard', {'workspacePaths': [str(case)], 'toolCall': {'args': {'TargetFile': str(source)}}}, ROOT)
        assert result.returncode == 0
        rows = [json.loads(s) for s in (case/'.lazyneon-workspace/audit_trail.jsonl').read_text().splitlines()]
        assert len(rows) == 1 and str(source) in json.dumps(rows)
    case = tmp_path/'unknown'; case.mkdir(); source = case/'source.txt'; source.write_text('x')
    result = hook('evidence_guard', {'toolCall': {'args': {'TargetFile': str(source)}}}, case)
    assert 'workspace missing' in result.stderr
    assert not (case/'.lazyneon-workspace').exists()

def test_anydoc_missing_dependency_does_not_launch_npx(monkeypatch, tmp_path):
    parser = load('scripts/parse_korean_doc.py')
    monkeypatch.setitem(sys.modules, 'anydoc', None)
    calls = []
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: calls.append(a))
    doc = tmp_path/'test.odp'; doc.write_bytes(b'')
    result = parser.parse_anydoc(str(doc))
    assert calls == []
    assert 'automatic network installation is disabled' in result['error']

def test_survey_real_audio_never_calls_google_without_consent(monkeypatch, tmp_path):
    import wave
    stt = load('scripts/local_stt.py')
    survey = load('scripts/case_survey.py')
    calls = []
    class Recognizer:
        def recognize_google(self, *args, **kwargs):
            calls.append('google')
            return 'stub'
    monkeypatch.setitem(sys.modules, 'speech_recognition', types.SimpleNamespace(Recognizer=Recognizer, AudioData=lambda *a: a))
    monkeypatch.setattr(stt.importlib.util, 'find_spec', lambda n: object() if n == 'speech_recognition' else None)
    monkeypatch.setattr(stt.shutil, 'which', lambda n: '/fake/ffmpeg' if n == 'ffmpeg' else None)
    monkeypatch.setattr(stt, '_probe_duration', lambda _: 1)
    run = subprocess.run
    monkeypatch.setattr(subprocess, 'run', lambda args, **kw: types.SimpleNamespace(stdout=b'0'*32000) if args[0] == 'ffmpeg' else run(args, **kw))
    original_load = survey._load
    monkeypatch.setattr(survey, '_load', lambda n: stt if n == 'local_stt' else original_load(n))
    with wave.open(str(tmp_path/'audio.wav'), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000); f.writeframes(b'0'*32000)
    result = survey.survey(tmp_path, [], True)
    assert calls == [], result['steps']['stt']
    assert '동의' in json.dumps(result['steps']['stt'], ensure_ascii=False)
    assert stt.main([str(tmp_path/'audio.wav'), '--engine', 'google-server']) == 2
    assert calls == []
    survey.survey(tmp_path, [], True, upload_audio=True)
    assert calls == ['google']

@pytest.mark.parametrize('entry', ['call_scribe', 'transcribe_one'])
def test_experimental_stt_uses_same_consent_gate(monkeypatch, tmp_path, entry):
    calls = []
    monkeypatch.setitem(sys.modules, 'requests', types.SimpleNamespace(post=lambda *a, **kw: calls.append('upload') or types.SimpleNamespace(status_code=200, json=lambda: {})))
    mod = load('experimental/video-editor/helpers/transcribe.py')
    monkeypatch.setattr(mod, 'extract_audio', lambda video, dest: dest.write_bytes(b'audio'))
    source = tmp_path/'audio.wav'; source.write_bytes(b'audio')
    args = (source, 'fake') if entry == 'call_scribe' else (source, tmp_path/'out', 'fake')
    with pytest.raises(PermissionError, match='--upload-audio'):
        getattr(mod, entry)(*args)
    assert calls == []
    getattr(mod, entry)(*args, allow_upload=True)
    assert calls == ['upload']
    assert mod.require_audio_upload_consent is __import__('audio_consent').require_audio_upload_consent
