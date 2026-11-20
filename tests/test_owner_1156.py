import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_verification_workspace_provenance(tmp_path):
    report = tmp_path / 'report.md'
    report.write_text('미확인')
    p = subprocess.run([sys.executable, str(ROOT/'scripts/verify_report.py'), str(report), '--json'], capture_output=True, text=True)
    meta = json.loads(p.stdout)['workspace_provenance']
    assert meta['workspace_version'] == json.loads((ROOT/'package.json').read_text())['version']
    assert len(meta['git_commit']) == 40
    assert isinstance(meta['git_dirty'], bool)

def test_artifact_workspace_provenance():
    sys.path.insert(0, str(ROOT/'scripts'))
    from generated_artifact import mark_artifact
    body = mark_artifact('sample', 'court_evidence_sheet')
    for field in ('workspace_version', 'git_commit', 'git_dirty'):
        assert field in body

def test_case_records_workspace_provenance(tmp_path):
    source = tmp_path/'source.txt'
    source.write_text('evidence')
    case = tmp_path/'case'
    def run(*args):
        return subprocess.run(['node', str(ROOT/'scripts/case_mode.mjs'), *map(str,args)], capture_output=True, text=True)
    assert run('init', source, '--out', case).returncode == 0
    try:
        assert run('close', '--case', case).returncode == 0
        records = [json.loads((case/'custody/hashes-start.json').read_text())]
        records += [json.loads(line) for line in (case/'custody/log.jsonl').read_text().splitlines()]
        records += [json.loads(line) for line in (case/'custody/protection.jsonl').read_text().splitlines()]
        for record in records:
            assert set(record['workspace_provenance']) == {'workspace_version', 'git_commit', 'git_dirty'}
    finally:
        run('unlock', '--case', case, '--reason', 'test cleanup')

def test_manifest_and_receipts_workspace_provenance(tmp_path):
    sys.path.insert(0, str(ROOT/'scripts'))
    from evidence_manifest import build_manifest
    from processing_receipt import make_receipt, build_receipt, utc_now_iso
    source=tmp_path/'e.txt'
    source.write_text('sample')
    records=[build_manifest(tmp_path), make_receipt(source, 'test'),
             build_receipt('id','test','1',source,source_base=tmp_path,started_at=utc_now_iso())]
    for record in records:
        assert set(record['workspace_provenance']) == {'workspace_version','git_commit','git_dirty'}

def test_provenance_unpackaged_unknown(tmp_path):
    sys.path.insert(0, str(ROOT/'scripts'))
    from workspace_provenance import workspace_provenance
    (tmp_path/'package.json').write_text('{"version":"1.2.3"}')
    assert workspace_provenance(tmp_path)=={'workspace_version':'1.2.3','git_commit':'unknown','git_dirty':'unknown'}

def test_other_forensic_verification_provenance(tmp_path):
    sys.path.insert(0, str(ROOT/'scripts'))
    from source_grounding import check
    from verify_claim_ledger import verify_claim_ledger_file
    from audit_evidence_integrity import audit, render_markdown
    results=[check('미확인', []), verify_claim_ledger_file(tmp_path/'missing.md'), audit([], ['sha256'])]
    for result in results:
        assert 'workspace_provenance' in result
    assert 'git_commit' in render_markdown(results[-1], ['sha256'], '', '2026-01-01')

def test_legal_verification_workspace_provenance(tmp_path):
    report=tmp_path/'legal.md'
    report.write_text('미확인')
    p=subprocess.run([sys.executable,str(ROOT/'scripts/verify_legal_factuality.py'),str(report),'--json'],capture_output=True,text=True)
    assert 'workspace_provenance' in json.loads(p.stdout)

def test_forensic_audit_and_timeline_provenance(tmp_path):
    import importlib.util
    def module(name, path):
        spec=importlib.util.spec_from_file_location(name,ROOT/path)
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    source=tmp_path/'source'
    source.write_text('sample')
    audit=module('audit_provenance','skills/forensic-audit/scripts/audit_timestamps.py')
    timeline=module('timeline_provenance','skills/forensic-timeline/scripts/generate_timeline.py')
    assert 'workspace_provenance' in audit.audit_file(source)
    assert 'git_commit' in timeline.generate_html([])

def test_templates_require_workspace_fields():
    for name in ['skills/report-guard/SKILL.md','skills/forensic-report/SKILL.md','templates/forensic_report_template.md']:
        text=(ROOT/name).read_text()
        for field in ['workspace_version','git_commit','git_dirty','scripts/workspace_provenance.py']:
            assert field in text

def test_specialized_reports_workspace_provenance(tmp_path):
    sys.path.insert(0,str(ROOT/'scripts'))
    from analyze_deepfake_evidence import generate_forensic_report, format_markdown_report
    from query_evidence_db import render_report
    from trace_financial_flow import render_markdown
    source=tmp_path/'sample.bin'
    source.write_bytes(b'sample')
    report=generate_forensic_report(str(source))
    assert 'workspace_provenance' in report
    outputs=[format_markdown_report(report), render_report([], '', []),
             render_markdown([], {'total_in':0,'total_out':0,'ranking':[]}, [], [], 7, 10)]
    assert all('git_commit' in output for output in outputs)
