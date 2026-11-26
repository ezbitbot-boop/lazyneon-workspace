"""Generated artifacts stay valid when saved with CRLF (Windows text mode, editors)."""
import json
import sys

from test_r6_workspace import ctx, run, event, ROOT  # noqa: F401

sys.path.insert(0, str(ROOT/'scripts'))
from generated_artifact import mark_artifact  # noqa: E402


def test_crlf_artifact_is_not_reported_as_changed(ctx):
    text = mark_artifact('# 증거 선조사 리포트 — originals\n생성: 2026-11-26 00:00\n', 'case_survey')
    report = ctx/'survey.md'
    report.write_bytes(text.replace('\n', '\r\n').encode('utf-8'))
    r = run('hallucination_guard.mjs', event(ctx, {'path': str(report)}))
    assert r.returncode == 0 and json.loads(r.stdout)['status'] == 'NOT_APPLICABLE', r.stdout + r.stderr


def test_crlf_artifact_body_edit_still_fails(ctx):
    text = mark_artifact('# 증거 선조사 리포트 — originals\n생성: 2026-11-26 00:00\n', 'case_survey')
    report = ctx/'survey.md'
    report.write_bytes(text.replace('\n', '\r\n').replace('originals', 'edited').encode('utf-8'))
    r = run('hallucination_guard.mjs', event(ctx, {'path': str(report)}))
    assert r.returncode == 1 and json.loads(r.stdout)['status'] == 'FAIL'
