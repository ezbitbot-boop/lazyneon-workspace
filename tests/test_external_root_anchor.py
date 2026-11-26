"""Owner decision: externally held evidence root, independent of local custody."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unicodedata

import pytest

ROOT = Path(__file__).resolve().parents[1]


def case(*args, env=None):
    return subprocess.run(['node', str(ROOT/'scripts/case_mode.mjs'), *map(str, args)],
                          text=True, capture_output=True, env={**os.environ, **(env or {})})


def setup_case(tmp_path, env=None):
    evidence = tmp_path/'evidence'
    evidence.mkdir()
    (evidence/'z.txt').write_text('last')
    (evidence/'e\u0301.txt').write_text('first')
    work = tmp_path/'case ; literal $value'
    result = case('init', evidence, '--out', work, env=env)
    assert result.returncode == 0, result.stderr
    baseline = json.loads((work/'custody/hashes-start.json').read_text())
    return evidence, work, baseline, result


def expected_root(evidence):
    rows = sorted([[unicodedata.normalize('NFC', str(p.relative_to(evidence))),
                    p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest()]
                   for p in evidence.rglob('*') if p.is_file()])
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def test_init_deterministic_root_and_identity(tmp_path):
    evidence, work, data, result = setup_case(tmp_path)
    expected = expected_root(evidence)
    assert f'ROOT HASH: {expected}' in result.stdout
    assert '이 컴퓨터 밖' in result.stdout
    assert data['rootHash'] == expected
    # Python's st_dev on Windows is the 64-bit volume serial; Node reports the 32-bit one.
    # The record is Node's, so compare with Node; the file ID is the same in both.
    node = subprocess.run(['node', '-e', "const s=require('fs').lstatSync(process.argv[1],{bigint:true});"
                           "console.log(String(s.dev),String(s.ino))", str(evidence)], capture_output=True, text=True, check=True)
    device, inode = node.stdout.split()
    assert inode == str(evidence.stat().st_ino)
    assert data['rootIdentity'] == {'device': device, 'inode': inode}
    other = tmp_path/'other'
    other.mkdir()
    _, _, second, _ = setup_case(other)
    assert second['rootHash'] == expected
    assert second['rootIdentity'] != data['rootIdentity']


@pytest.mark.parametrize('command', ['close', 'verify'])
def test_external_root_detects_evidence_and_baseline_rewrite(tmp_path, command):
    evidence, work, data, _ = setup_case(tmp_path)
    root = expected_root(evidence)
    assert case('unlock', '--case', work, '--reason', 'regression tamper').returncode == 0
    (evidence/'z.txt').write_text('tampered')
    for row in data['files']:
        p = Path(row['path'])
        row.update(sha256=hashlib.sha256(p.read_bytes()).hexdigest(), sizeBytes=p.stat().st_size)
    data.pop('protection', None)  # attacker also rewrites local protection claims
    data['rootHash'] = expected_root(evidence)
    (work/'custody/hashes-start.json').write_text(json.dumps(data))
    result = case(command, '--case', work, '--expect-root', root)
    assert result.returncode != 0
    assert 'ROOT HASH MISMATCH' in result.stderr


def test_close_without_anchor_discloses_limit(tmp_path):
    evidence, work, _, _ = setup_case(tmp_path)
    result = case('close', '--case', work)
    assert result.returncode == 0, result.stderr
    assert f'ROOT HASH: {expected_root(evidence)}' in result.stdout
    assert '로컬 기록만으로는 무결성을 증명할 수 없습니다' in result.stdout
    assert case('verify', '--case', work, '--expect-root', expected_root(evidence)).returncode == 0
    invalid = case('close', '--case', work, '--expect-root', 'bad')
    assert invalid.returncode == 2


@pytest.mark.skipif(os.name == 'nt', reason="runs a '#!' script as the anchor command; Windows cannot execute shebang files")
@pytest.mark.parametrize('exit_status', [0, 7])
def test_anchor_exact_argv_once_and_failure_nonfatal(tmp_path, exit_status):
    hook = tmp_path/'anchor with spaces'
    receipt = tmp_path/'anchor-args.jsonl'
    hook.write_text('#!/usr/bin/env node\nconst fs=require("fs");\n'
                    'fs.appendFileSync(process.env.ANCHOR_RECEIPT, JSON.stringify(process.argv.slice(2))+"\\n");\n'
                    f'process.exit({exit_status});\n')
    hook.chmod(0o700)
    evidence, work, data, result = setup_case(tmp_path, {'LAZYNEON_WS_ANCHOR_CMD': str(hook), 'ANCHOR_RECEIPT': str(receipt)})
    calls = [json.loads(line) for line in receipt.read_text().splitlines()]
    assert calls == [[expected_root(evidence), data['caseId'], data['timestamp']]]
    assert re.fullmatch(r'.*Z', calls[0][2])
    log = [json.loads(line) for line in (work/'custody/log.jsonl').read_text().splitlines()]
    anchor = [row for row in log if row['type'] == 'anchor']
    assert len(anchor) == 1 and anchor[0]['exitStatus'] == exit_status
    assert ('[미확인] anchor' in result.stderr) == bool(exit_status)
    assert case('verify', '--case', work, '--expect-root', expected_root(evidence)).returncode == 0
    assert len(receipt.read_text().splitlines()) == 1


def test_anchor_spawn_failure_nonfatal(tmp_path):
    _, work, _, result = setup_case(tmp_path, {'LAZYNEON_WS_ANCHOR_CMD': str(tmp_path/'missing')})
    assert '[미확인] anchor' in result.stderr
    events = [json.loads(line) for line in (work/'custody/log.jsonl').read_text().splitlines()]
    assert events[-1]['type'] == 'anchor' and events[-1]['exitStatus'] is None


def test_report_integrity_requires_root(tmp_path):
    evidence, work, data, _ = setup_case(tmp_path)
    report = work/'report.md'
    def verify(text):
        report.write_text(text)
        result = subprocess.run([sys.executable, str(ROOT/'scripts/verify_report.py'), str(report),
                                 '--evidence', str(work/'custody/hashes-start.json'), '--json'], text=True, capture_output=True)
        return result, json.loads(result.stdout)
    title = '# 디지털포렌식 분석 보고서\n'
    for content in [title, title+'## 무결성\n미측정\n', title+f'ROOT HASH: {expected_root(evidence)}\n## 무결성\n없음\n']:
        result, payload = verify(content)
        assert result.returncode == 1 and any('ROOT HASH' in e for e in payload['errors'])
    result, payload = verify(title+'## 무결성\nROOT HASH: '+expected_root(evidence)+'\n')
    assert result.returncode == 0, payload
    result, payload = verify(title+'## 무결성\nROOT HASH: '+'0'*64+'\n')
    assert result.returncode == 1


def test_template_and_docs_explain_external_trust():
    template = (ROOT/'templates/forensic_report_template.md').read_text()
    assert '무결성' in template and 'ROOT HASH:' in template
    for name in ['README.md', 'skills/case-mode/SKILL.md']:
        text = (ROOT/name).read_text()
        for required in ['같은 OS 사용자', '--expect-root', 'LAZYNEON_WS_ANCHOR_CMD', '이 컴퓨터 밖']:
            assert required in text
    assert 'ROOT HASH' in (ROOT/'skills/report-guard/SKILL.md').read_text()


def test_report_rejects_file_hash_mislabeled_as_root(tmp_path):
    _, work, data, _ = setup_case(tmp_path)
    report = work/'report.md'
    report.write_text('# 디지털포렌식 보고서\n## 무결성\nROOT HASH: '+data['files'][0]['sha256']+'\n')
    result = subprocess.run([sys.executable, str(ROOT/'scripts/verify_report.py'), str(report),
                             '--evidence', str(work/'custody/hashes-start.json'), '--json'], text=True, capture_output=True)
    assert result.returncode == 1 and 'ROOT HASH' in result.stdout
