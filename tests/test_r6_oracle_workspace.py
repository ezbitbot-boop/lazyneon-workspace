"""Oracle regressions through the configured hooks, using real local guards."""
import json
import re
import shlex
import subprocess
import pytest
from test_r6_workspace import ROOT, GUARDS, ctx, event, run


# PreInvocation deletes the queue it delivers; post() keeps what it saw for assertions.
DELIVERED = {}


def queued(ctx):
    return [json.loads(line) for p in (ctx/'.lazyneon-workspace/feedback').glob('*.jsonl')
            for line in p.read_text().splitlines()]


def rows(ctx):
    return DELIVERED.get(str(ctx), []) + queued(ctx)


def dispatch(stage, payload):
    outputs = []
    for entry in json.loads((ROOT/'hooks.json').read_text())['hooks'][stage]:
        if 'matcher' in entry and not re.search(entry['matcher'], payload['toolCall']['name']):
            continue
        for hook in entry.get('hooks', [entry]):
            result = subprocess.run(shlex.split(hook['command']), cwd=ROOT,
                                    input=json.dumps(payload), text=True,
                                    capture_output=True, timeout=35)
            outputs.append(result)
    assert outputs
    return outputs


def post(ctx, patch):
    payload = event(ctx, {'patch': '*** Begin Patch\n'+patch+'\n*** End Patch'}, 'apply_patch')
    assert all(r.returncode == 0 for r in dispatch('PostToolUse', payload))
    DELIVERED.setdefault(str(ctx), []).extend(queued(ctx))
    delivered = json.loads(dispatch('PreInvocation', payload)[0].stdout)
    assert queued(ctx) == []
    return delivered


def test_deleted_patch_target_has_no_content_verdict(ctx):
    assert post(ctx, '*** Delete File: notes.md') == {}
    assert not any(r['kind'] in ('fail', 'warn') for r in rows(ctx))


def test_patch_move_checks_only_destination(ctx):
    (ctx/'new.md').write_text('ordinary notes')
    assert post(ctx, '*** Update File: old.md\n*** Move to: new.md') == {}
    checked = [r for r in rows(ctx) if r['kind'] != 'skip']
    assert len(checked) == 4
    assert {r['target'] for r in checked} == {str(ctx/'new.md')}


def test_missing_move_destination_still_fails(ctx):
    out = post(ctx, '*** Update File: old.md\n*** Move to: absent.md')
    assert '미확인' in str(out)
    failures = [r for r in rows(ctx) if r['kind'] == 'unchecked']
    assert len(failures) == 4
    assert {r['target'] for r in failures} == {str(ctx/'absent.md')}


def test_missing_write_still_fails(ctx):
    payload = event(ctx, {'path': 'absent.md'})
    dispatch('PostToolUse', payload)
    assert len(rows(ctx)) == 4
    assert all(r['kind'] == 'unchecked' for r in rows(ctx))
    assert '미확인' in dispatch('PreInvocation', payload)[0].stdout


@pytest.mark.parametrize('patch', [
    '*** Delete File: evidence/old.raw',
    '*** Update File: evidence/old.raw\n*** Move to: notes.md',
    '*** Update File: notes.md\n*** Move to: evidence/new.raw',
    '*** Delete File: .lazyneon/evidence/old.raw',
    '*** Update File: .lazyneon/evidence/old.raw\n*** Move to: notes.md',
    '*** Update File: notes.md\n*** Move to: .lazyneon/evidence/new.raw',
])
def test_patch_evidence_delete_and_move_denied(ctx, patch):
    result = dispatch('PreToolUse', event(ctx, {'patch': patch}, 'apply_patch'))[0]
    assert result.returncode == 1
    assert json.loads(result.stdout)['decision'] == 'deny'


@pytest.mark.parametrize('relative', [
    '.lazyneon/ulw-research/소장.md', '.lazyneon/report.md',
    '.lazyneon/feedback/소장.md', '.lazyneon/logs/소장.md',
    '.lazyneon/lookups/소장.md', '.lazyneon/pins.md.backup',
])
def test_lazyneon_user_reports_are_checked(ctx, relative):
    target = ctx/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('민법 제1500조.')
    payload = event(ctx, {'path': str(target)}, 'mcp__files__write_file')
    dispatch('PostToolUse', payload)
    assert len(rows(ctx)) == 4
    assert {r['target'] for r in rows(ctx)} == {str(target)}
    if target.suffix == '.md':
        assert any(r['guard'] == 'legal_factuality_guard.mjs' and r['kind'] == 'fail' for r in rows(ctx))
        assert 'FAIL' in dispatch('PreInvocation', payload)[0].stdout


@pytest.mark.parametrize('relative', [
    'pins.md', 'ulw-scope.md', 'ulw-dag.json', 'lookups.jsonl',
    'feedback/session.jsonl', 'logs/session.log',
])
def test_core_state_stays_excluded(ctx, relative):
    target = ctx/'.lazyneon'/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('민법 제1500조.')
    payload = event(ctx, {'path': str(target)})
    dispatch('PostToolUse', payload)
    assert dispatch('PreInvocation', payload)[0].stdout.strip() == '{}'
    assert rows(ctx) == []


def test_symlinked_lazyneon_report_is_checked(ctx):
    folder = ctx/'.lazyneon/ulw-research'
    folder.mkdir(parents=True)
    (ctx/'alias').symlink_to(folder, target_is_directory=True)
    (folder/'소장.md').write_text('민법 제1500조.')
    payload = event(ctx, {'path': 'alias/소장.md'})
    dispatch('PostToolUse', payload)
    assert any(r['kind'] == 'fail' for r in rows(ctx))


@pytest.mark.parametrize('guard', GUARDS)
def test_direct_patch_dispatch_checks_move_destination(ctx, guard):
    target = ctx/'소장_보고서.md'
    target.write_text('민법 제1500조 명백히 입증 '+'a'*64)
    args = ['post-tool-use'] if guard == GUARDS[0] else []
    patch = event(ctx, {'patch': '*** Update File: old.md\n*** Move to: 소장_보고서.md'}, 'apply_patch')
    result = run(guard, patch, *args)
    # Separate workspace keeps one-time timeline notices independent.
    control_workspace = ctx/'control-workspace'
    control_workspace.mkdir()
    control = run(guard, event(control_workspace, {'path': str(target)}), *args)
    assert result.returncode == control.returncode
    assert result.stderr == control.stderr
    if guard == GUARDS[0]:
        assert '소장_보고서.md' in (ctx/'.lazyneon-workspace/audit_trail.jsonl').read_text()
    else:
        assert 'GUARD' in result.stderr


def test_mixed_patch_keeps_writes_and_move_destination(ctx):
    (ctx/'new.md').write_text('민법 제1500조.')
    (ctx/'added.md').write_text('ordinary notes')
    out = post(ctx, '*** Delete File: gone.md\n*** Update File: old.md\n*** Move to: new.md\n*** Add File: added.md\n+ordinary notes')
    assert 'FAIL' in str(out)
    assert len(rows(ctx)) == 8
    assert {r['target'] for r in rows(ctx)} == {str(ctx/'new.md'), str(ctx/'added.md')}
    assert any(r['guard'] == 'legal_factuality_guard.mjs' and r['kind'] == 'fail' for r in rows(ctx))


@pytest.mark.parametrize('patch', [
    '--- a/old.md\n+++ /dev/null',
    '--- a/old.md\n+++ b/new.md',
])
def test_unified_patch_content_targets(ctx, patch):
    (ctx/'new.md').write_text('ordinary notes')
    assert post(ctx, patch) == {}
    assert all(r['target'] == str(ctx/'new.md') for r in rows(ctx))
