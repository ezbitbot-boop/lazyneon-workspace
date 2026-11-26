"""Offline round-4 security contracts (real guards, files and PDF engine)."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unicodedata
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import report_core
import mask_korean_pii as pii
import pii_mask


@pytest.fixture(autouse=True)
def isolated_feedback_home(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))  # os.homedir() on Windows

def node(script, *args, payload=None, cwd=ROOT):
    return subprocess.run(['node', str(ROOT/'scripts'/script), *map(str, args)], input=json.dumps(payload or {}), text=True, capture_output=True, cwd=cwd, env={**os.environ, 'LAZYNEON_WS_PYTHON': sys.executable}, timeout=60)

@pytest.mark.parametrize('command', ['git config --file evidence/chat.txt user.name injected', 'python /tmp/verify_report.py evidence/chat.txt'])
def test_untrusted_readonly_commands_denied(command):
    r = node('evidence_guard.mjs', 'pre-tool-use', payload={'toolCall': {'name':'run_command','args':{'CommandLine':command}}})
    assert r.returncode != 0 and 'deny' in r.stdout

def test_trusted_verifier_allowed():
    r = node('evidence_guard.mjs', 'pre-tool-use', payload={'toolCall': {'name':'run_command','args':{'CommandLine':f'python "{ROOT}/scripts/verify_report.py" evidence/chat.txt'}}})
    assert r.returncode == 0

@pytest.mark.parametrize('suffixes', [('E01','E03'),('e01','e02'),('EX01','EX02'),('AD1','AD2'),('E01','EAA')])
def test_case_all_segments_and_additions(tmp_path, suffixes):
    for suffix in suffixes: (tmp_path/f'disk.{suffix}').write_text(suffix)
    case = tmp_path/'case'
    assert node('case_mode.mjs','init',tmp_path/f'disk.{suffixes[0]}','--out',case).returncode == 0
    rows = json.loads((case/'custody/hashes-start.json').read_text())['files']
    assert len(rows) == 2
    assert node('case_mode.mjs','unlock','--case',case,'--reason','simulate segment tampering').returncode == 0
    (tmp_path/'disk.E04' if suffixes[0].lower() == 'e01' else tmp_path/f'disk.{suffixes[1]}').write_text('new')
    closed = node('case_mode.mjs','close','--case',case)
    assert closed.returncode != 0
    assert ('NEW' if suffixes[0].lower() == 'e01' else 'CHANGED') in closed.stderr

@pytest.mark.parametrize('target', ['file','directory','outside','missing'])
def test_case_links_recorded_without_following(tmp_path, target):
    evidence = tmp_path/'evidence'; evidence.mkdir()
    dest = tmp_path/target
    if target == 'directory': dest.mkdir()
    elif target != 'missing': dest.write_text('source')
    link = evidence/'link'; link.symlink_to(dest)
    case = tmp_path/'case'
    # r10: link metadata alone must never certify target content integrity.
    result = node('case_mode.mjs','init',evidence,'--out',case)
    assert result.returncode != 0 and 'Symlink' in result.stderr
    assert not case.exists()
    assert link.is_symlink()
    if target not in ['directory','missing']: assert dest.read_text() == 'source'
    link.unlink(); link.symlink_to(tmp_path/'other')
    result = node('case_mode.mjs','init',evidence,'--out',case)
    assert result.returncode != 0 and not case.exists()

def test_case_baseline_immutable(tmp_path):
    src = tmp_path/'src'; src.write_text('original'); case = tmp_path/'case'
    assert node('case_mode.mjs','init',src,'--out',case).returncode == 0
    baseline = case/'custody/hashes-start.json'; before = baseline.read_bytes()
    assert node('case_mode.mjs','unlock','--case',case,'--reason','simulate baseline tampering').returncode == 0
    src.write_text('modified')
    assert node('case_mode.mjs','init',src,'--out',case).returncode != 0
    assert baseline.read_bytes() == before
    closed = node('case_mode.mjs','close','--case',case)
    assert closed.returncode != 0 and 'CHANGED' in closed.stderr

@pytest.mark.parametrize('offset', [-10, 0, 10])
def test_truncated_report_fails_closed(tmp_path, offset):
    report = tmp_path/'r.md'; report.write_text('a'*(8*1024*1024+offset)+' 명백히 입증 '+ 'b'*64)
    r = subprocess.run([sys.executable,str(ROOT/'scripts/verify_report.py'),str(report),'--json'],capture_output=True,text=True)
    assert r.returncode != 0
    assert '크기 제한' in r.stdout

@pytest.mark.parametrize('value', ['010\u200b-1234-5678', '900101−1234567', '110 123 456789', '+82 10-1234-5678', '+82-10-1234-5678', '0082 10 1234 5678', '０１０−１２３４-５６７８', '01０-١٢٣٤-5678'])
def test_pii_variants_mask_and_vault(value, tmp_path):
    masked, stats = pii.mask_text(value,pii.ALL_TYPES,mask_suspect_rrn=True)
    assert masked != value and '*' in masked
    vault = pii.PiiVault(); tokenized, _ = vault.tokenize_text(value,pii.ALL_TYPES,mask_suspect_rrn=True)
    assert tokenized.startswith('[PII_') and tokenized.endswith(']')
    assert vault.detokenize_text(tokenized) == value
    assert pii_mask.detect_in_text(value)
    assert pii_mask.mask_text(value) != value
    assert_private_digits_hidden(value, masked, phone_secret='5678')
    assert_private_digits_hidden(value, pii_mask.mask_text(value))
    source = tmp_path/'pii.txt'; source.write_text(value)
    output = tmp_path/'masked.txt'
    cli = subprocess.run([sys.executable, str(ROOT/'scripts/pii_mask.py'), str(source), '--mask', '-o', str(output), '--json'], capture_output=True, text=True)
    assert cli.returncode == 1  # PII found, successfully masked.
    assert json.loads(cli.stdout)['total_pii'] > 0
    assert_private_digits_hidden(value, output.read_text())
    assert source.read_text() == value

@pytest.mark.parametrize('name', ['김하은','김\u200b철수',unicodedata.normalize('NFD','김하은')])
def test_whole_name_tokenized(name):
    text = '성명: '+name
    vault = pii.PiiVault(); masked,_ = vault.tokenize_text(text,pii.ALL_TYPES)
    assert masked == '성명: [PII_NAME_1]'
    assert vault.detokenize_text(masked) == text

def test_foreign_and_driver_detection():
    for value in ['900101-5234567','11-22-123456-01']:
        masked,stats=pii.mask_text(value,pii.DEFAULT_TYPES)
        assert masked != value
        assert pii_mask.detect_in_text(value)

def test_pii_negative_text_unchanged():
    value = '날짜 2026-03-01, 버전 1.2.3, 금액 123원; 일반 문장'
    assert pii.mask_text(value,pii.ALL_TYPES)[0] == value
    assert pii_mask.mask_text(value) == value

@pytest.mark.parametrize('status', ['failed','partial','complete'])
def test_unverified_receipt_cannot_ground(tmp_path,status):
    from processing_receipt import make_receipt
    source=tmp_path/'s'; source.write_text('original')
    receipt=make_receipt(source,'test'); digest=receipt['source']['sha256']; receipt['status']=status
    if status=='complete': source.write_text('tampered')
    evidence=tmp_path/'receipt.json'; evidence.write_text(json.dumps({'processing_receipt':receipt}))
    assert digest not in report_core.load_evidence_hashes(evidence)

@pytest.mark.parametrize('bad', ['chain','hmac'])
def test_broken_audit_cannot_ground(tmp_path,bad,monkeypatch):
    digest='a'*64
    row={'timestamp':'now','file':'s','sha256':digest,'prev_hash': 'b'*64 if bad=='chain' else None}
    if bad=='hmac': row['hmac']='c'*64; monkeypatch.setenv('LAZYNEON_WS_HMAC_KEY','secret')
    p=tmp_path/'audit_trail.jsonl'; p.write_text(json.dumps(row)+'\n')
    assert digest not in report_core.load_evidence_hashes(p)

def test_morph_engine_absent_not_pass(tmp_path):
    # -S alone still imports optional packages supplied through PYTHONPATH.
    p=tmp_path/'r.md'; p.write_text('피해자는 현장을 떠났다.')
    r=subprocess.run([sys.executable,'-S',str(ROOT/'tests/morph_without_engine.py'),str(ROOT/'scripts/verify_report.py'),str(p),'--evidence',str(p),'--morph-grounding','--json'],capture_output=True,text=True)
    assert r.returncode != 0 and 'kiwipiepy' in r.stdout
    assert 'MORPH_UNAVAILABLE' in json.loads(r.stdout)['status_codes']
    assert '[미확인]' in r.stdout

@pytest.mark.parametrize('tool', ['write_file','call_mcp_tool','CallMcpTool','mcp__document__write_file'])
def test_post_feedback_reaches_model(tmp_path,tool):
    import re
    hooks=json.loads((ROOT/'hooks.json').read_text())['hooks']
    assert re.fullmatch(hooks['PostToolUse'][0]['matcher'],tool)
    assert all('domain_feedback.mjs batch' in h['command'] for group in hooks['PostToolUse'] for h in group['hooks'])
    p=tmp_path/'소장.md'; p.write_text('민법 제1500조에 기하여 청구한다.')
    payload={'workspacePaths':[str(tmp_path)],'conversationId':'one','tool_name':tool,'tool_input':{'server':'kordoc','tool':'fill_form','args':{'path':str(p)}} if tool in {'call_mcp_tool','CallMcpTool'} else {'path':str(p)}}
    r=node('domain_feedback.mjs','batch','evidence_guard.mjs','hallucination_guard.mjs','legal_factuality_guard.mjs','slop_guard.mjs',payload=payload)
    assert r.returncode == 0 and r.stdout.strip() == '{}'
    assert node('domain_feedback.mjs','inject',payload={**payload,'conversationId':'two'}).stdout.strip() == '{}'
    result=node('domain_feedback.mjs','inject',payload=payload)
    assert 'legal_factuality_guard' in result.stdout and 'FAIL' in result.stdout and 'ephemeralMessage' in result.stdout
    assert 'injectSteps' in result.stdout

def test_legacy_operational_paths_already_removed():
    for name in ['sync_guard_pack.sh','stop_claim_guard.mjs','markdown_structure_guard.mjs']:
        assert not (ROOT/'scripts'/name).exists()
    for folder in ['scripts','test','tests']:
        for p in (ROOT/folder).glob('*'):
            if p.is_file() and p.suffix in {'.py','.mjs','.sh'} and p.name != Path(__file__).name:
                assert 'lazyargon' not in p.read_text().lower(), p

@pytest.mark.parametrize('operation', ['read_document','get_document'])
def test_mcp_reads_do_not_validate_stale_report(tmp_path,operation):
    p=tmp_path/'소장.md'; p.write_text('민법 제1500조')
    payload={'workspacePaths':[str(tmp_path)],'conversationId':'read','tool_name':'call_mcp_tool','tool_input':{'tool':operation,'args':{'path':str(p)}}}
    r=node('domain_feedback.mjs','batch','legal_factuality_guard.mjs',payload=payload)
    assert r.returncode==0 and r.stdout.strip()=='{}'

def test_mcp_missing_target_is_unverified(tmp_path):
    r=node('domain_feedback.mjs','batch','legal_factuality_guard.mjs',payload={'workspacePaths':[str(tmp_path)],'conversationId':'missing','tool_name':'call_mcp_tool','tool_input':{'tool':'fill_form','args':{}}})
    assert r.returncode==0 and r.stdout.strip()=='{}'
    injected=node('domain_feedback.mjs','inject',payload={'conversationId':'missing'})
    assert '미확인' in injected.stdout

def test_valid_receipt_and_chain_can_ground(tmp_path,monkeypatch):
    import hmac
    from processing_receipt import make_receipt
    source=tmp_path/'s'; source.write_text('actual evidence')
    receipt=make_receipt(source,'test'); digest=receipt['source']['sha256']
    p=tmp_path/'receipt.json'; p.write_text(json.dumps({'processing_receipt':receipt}))
    assert digest in report_core.load_evidence_hashes(p)
    monkeypatch.setenv('LAZYNEON_WS_HMAC_KEY','secret')
    row={'timestamp':'now','file':str(source),'sha256':digest,'prev_hash':None}
    row['hmac']=hmac.new(b'secret',f'now|{source}|{digest}|'.encode(),hashlib.sha256).hexdigest()
    p.write_text(json.dumps(row)+'\n')
    assert digest in report_core.load_evidence_hashes(p)

def test_truncated_evidence_cannot_supply_hashes(tmp_path):
    p=tmp_path/'evidence.txt'; digest='a'*64
    p.write_text(digest+'\n'+'x'*(8*1024*1024))
    assert digest not in report_core.load_evidence_hashes(p)

def test_feedback_is_deleted_once_delivered(tmp_path):
    p=tmp_path/'소장.md'; p.write_text('민법 제1500조')
    payload={'workspacePaths':[str(tmp_path)],'conversationId':'retained','tool_name':'write_file','tool_input':{'path':str(p)}}
    node('domain_feedback.mjs','batch','legal_factuality_guard.mjs',payload=payload)
    feedback=tmp_path/'.lazyneon-workspace/feedback'
    queues=list(feedback.glob('*.jsonl')); assert len(queues)==1
    assert 'injectSteps' in node('domain_feedback.mjs','inject',payload=payload).stdout
    assert list(feedback.iterdir())==[]
    assert node('domain_feedback.mjs','inject',payload=payload).stdout.strip()=='{}'

def test_unlinked_audit_record_rejected(tmp_path):
    p=tmp_path/'audit_trail.jsonl'; digest='a'*64
    p.write_text(json.dumps({'file':'s','sha256':digest})+'\n')
    assert digest not in report_core.load_evidence_hashes(p)
    assert digest not in report_core.load_evidence_hash_file_pairs([str(p)])

def test_large_evidence_prevents_report_pass(tmp_path):
    p=tmp_path/'r.md'; p.write_text('관찰 내용')
    ev=tmp_path/'evidence.txt'; ev.write_text('x'*(8*1024*1024+1))
    r=subprocess.run([sys.executable,str(ROOT/'scripts/verify_report.py'),str(p),'--evidence',str(ev),'--json'],capture_output=True,text=True)
    assert r.returncode!=0 and '크기 제한' in r.stdout

@pytest.mark.parametrize('value', ['900101 - 1234567','010 - 1234 - 5678','+82 10 - 1234 - 5678','９００１０１ − ５２３４５６７','１１ − ２２ − １２３４５６ − ０１'])
def test_spaced_mixed_separators(value, tmp_path):
    masked,_=pii.mask_text(value,pii.ALL_TYPES,mask_suspect_rrn=True)
    assert masked!=value and '*' in masked
    vault=pii.PiiVault(); tokens,_=vault.tokenize_text(value,pii.ALL_TYPES,mask_suspect_rrn=True)
    assert tokens.startswith('[PII_') and tokens.endswith(']')
    assert vault.detokenize_text(tokens)==value
    assert pii_mask.detect_in_text(value)
    assert pii_mask.mask_text(value)!=value
    assert_private_digits_hidden(value, masked, phone_secret='5678')
    assert_private_digits_hidden(value, pii_mask.mask_text(value))
    source = tmp_path/'pii.txt'; source.write_text(value)
    output = tmp_path/'masked.txt'
    cli = subprocess.run([sys.executable, str(ROOT/'scripts/pii_mask.py'), str(source), '--mask', '-o', str(output), '--json'], capture_output=True, text=True)
    assert cli.returncode == 1  # PII found, successfully masked.
    assert json.loads(cli.stdout)['total_pii'] > 0
    assert_private_digits_hidden(value, output.read_text())
    assert source.read_text() == value


def assert_private_digits_hidden(value, masked, phone_secret='1234'):
    # Independent of the production normalizer: no format/control character
    # can hide leaked middle/account/RRN digits from this assertion.
    digits = lambda text: ''.join(str(unicodedata.decimal(c)) for c in text if c.isdecimal())
    secret = '234567' if '900101' in digits(value) else ('456789' if digits(value).startswith('110') else phone_secret)
    assert secret not in digits(masked)
    assert digits(value) not in digits(masked)
