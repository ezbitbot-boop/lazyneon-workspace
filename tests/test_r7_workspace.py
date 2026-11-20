"""Offline execution contracts for review r7; subprocess fakes only at dependency boundaries."""
import json
import os
import subprocess
import sys
import pytest
from test_r6_workspace import ROOT, ctx, run, event, batch, rows

@pytest.mark.parametrize('guard', ['hallucination_guard.mjs', 'legal_factuality_guard.mjs'])
@pytest.mark.parametrize('failure', ['missing', 'clt', 'store', 'dependency', 'silent', 'crash'])
def test_unavailable_verifier_blocks_and_relays(ctx, guard, failure):
    report = ctx/'감정보고서_소장.md'
    report.write_text('# 감정 보고서 SHA-256 소장 청구원인')
    interpreter = ctx/'python-stub'
    if failure != 'missing':
        body = {
            'clt': 'import sys; sys.stderr.write("xcode-select: No developer tools"); sys.exit(1)',
            'store': 'import sys; sys.stderr.write("Python was not found; Microsoft Store"); sys.exit(1)',
            'dependency': 'import missing_r7_verifier_dependency',
            'silent': 'pass',
            'crash': 'import os, signal; os.kill(os.getpid(), signal.SIGKILL)',
        }[failure]
        interpreter.write_text('#!'+sys.executable+'\n'+body+'\n')
        interpreter.chmod(0o755)
    env = {'LAZYNEON_WS_PYTHON': str(interpreter)}
    payload = event(ctx, {'path': str(report)})
    result = run(guard, payload, env=env)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert json.loads(result.stdout)['decision'] == 'block'
    batch(payload, guard, env=env)
    assert rows(ctx)[-1]['kind'] == 'unchecked'
    message = json.loads(run('domain_feedback.mjs', payload, 'inject').stdout)['injectSteps'][0]['ephemeralMessage']
    assert '미확인' in message or 'FAIL' in message

@pytest.mark.parametrize('guard', ['hallucination_guard.mjs', 'legal_factuality_guard.mjs'])
def test_ordinary_edit_needs_no_python(ctx, guard):
    (ctx/'shopping.txt').write_text('shopping list')
    result = run(guard, event(ctx, {'path': 'shopping.txt'}), env={'LAZYNEON_WS_PYTHON':str(ctx/'absent')})
    assert result.returncode == 0
    assert json.loads(result.stdout) == {'status':'NOT_APPLICABLE'}

@pytest.mark.parametrize('pip_status', [0, 17])
def test_setup_entrypoint_records_install_and_failure(tmp_path, pip_status):
    home = tmp_path/'빈 HOME'; home.mkdir()
    record = tmp_path/'pip.json'
    # Run the real CLI and real venv creation, replacing only package installation
    # with a recording boundary (no network, no third-party packages).
    harness = '''
import json, pathlib, runpy, subprocess, sys, venv
create = venv.create
def offline_create(path, **kwargs):
    create(path, with_pip=False)
venv.create = offline_create
record, status, script = sys.argv[1:]
sys.argv = [script, '--with', 'imaging', 'morph']
# Preserve recording arguments outside the CLI argv.
def pip_record(argv, **kwargs):
    pathlib.Path(record).write_text(json.dumps(argv))
    return subprocess.CompletedProcess(argv, int(status), '', 'R7_PIP_FAILURE')
subprocess.run = pip_record
runpy.run_path(script, run_name='__main__')
'''
    result = subprocess.run([sys.executable, '-c', harness, str(record), str(pip_status), str(ROOT/'scripts/setup_forensic_env.py')], env={**os.environ,'HOME':str(home), 'USERPROFILE':str(home)}, text=True, capture_output=True, timeout=30)
    assert record.exists(), (result.stdout, result.stderr)
    argv = json.loads(record.read_text())
    env_dir = home/'.lazyneon-workspace/venv'
    assert (env_dir/'pyvenv.cfg').is_file()
    assert argv == [str(env_dir/('Scripts/pip' if sys.platform=='win32' else 'bin/pip')), 'install', '-r', str(ROOT/'requirements.txt'), 'pillow>=10.0,<12', 'numpy>=1.26,<3', 'kiwipiepy>=0.20,<1']
    assert result.returncode == (1 if pip_status else 0), result.stderr
    if pip_status:
        assert 'R7_PIP_FAILURE' in result.stderr
        assert '완료.' not in result.stdout
    else:
        assert str(env_dir/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')) in result.stdout

@pytest.mark.parametrize('guard', ['hallucination_guard.mjs', 'legal_factuality_guard.mjs'])
def test_missing_verifier_script_blocks(ctx, guard):
    import shutil
    scripts = ctx/'plugin/scripts'; scripts.mkdir(parents=True)
    for source in (ROOT/'scripts').glob('*.mjs'):
        shutil.copy2(source, scripts/source.name)
    report = ctx/'감정보고서_소장.md'; report.write_text('감정 보고서 소장 청구원인')
    result = subprocess.run(['node', str(scripts/guard)], input=json.dumps(event(ctx, {'path':str(report)})), capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    assert 'NOT_CHECKED' in result.stderr
    assert json.loads(result.stdout)['decision'] == 'block'
