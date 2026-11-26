"""Improvement brief regressions; no model/network calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from evidence_output import within
from evidence_manifest import build_manifest, verify_manifest

@pytest.mark.parametrize('root,child,outside', [
    (r'C:\case\evidence', r'c:\CASE\evidence\report.json', r'C:\case\evidence-other\x'),
    (r'\\server\share\evidence', r'\\SERVER\share\evidence\x', r'\\server\share\evidence2\x'),
])
def test_windows_evidence_boundary(root, child, outside):
    assert within(child, root)
    assert not within(outside, root)
    assert not within(r'D:\case\evidence\x', root)

@pytest.mark.parametrize('ancestor', ['ordinary', '__pycache__'])
def test_manifest_includes_cache_named_evidence(tmp_path, ancestor):
    root=tmp_path/ancestor/'evidence'; folder=root/'__pycache__'; folder.mkdir(parents=True)
    sample=folder/'payload.bin'; sample.write_bytes(b'original')
    manifest=build_manifest(root)
    assert manifest['file_count']==1
    sample.write_bytes(b'changed')
    assert any(p.startswith('CHANGED:') for p in verify_manifest(root,manifest))
    (folder/'added.bin').write_bytes(b'new')
    assert any(p.startswith('NEW:') for p in verify_manifest(root,manifest))

def test_shared_windows_python_probe_contract():
    selector=ROOT/'scripts/select_python.ps1'
    assert selector.exists()
    text=selector.read_text()
    for required in ['WaitForExit', 'Kill()', '-3.12', 'sys.version_info', '3, 12', 'LAZYNEON_WS_PYTHON', '$stdout.Result.Trim()', '$stdout.Wait(200)']:
        assert required in text
    for name in ['bin/lazyforensic.ps1','bin/lazyothers.ps1','scripts/py.ps1','scripts/setup_forensic_env.ps1']:
        text=(ROOT/name).read_text()
        assert 'select_python.ps1' in text and '@PyArgs' in text
        assert 'Get-Command python' not in text

def test_release_docs_and_domain_exclusion():
    for name in ['plugin.json','package.json']:
        data=json.loads((ROOT/name).read_text())
        assert data['version']=='0.2.2'
        assert data['requires']=={'lazyneon':'>=0.3.0'}
    for skill in (ROOT/'skills').glob('*/SKILL.md'):
        assert 'gemini-4-hydrogen' in skill.read_text(), skill
        assert 'Neon' in skill.read_text()
    readme=(ROOT/'README.md').read_text()
    for text in ['Install both (recommended)', 'git clone', 'PowerShell', '한국어 규칙 적용 범위']:
        assert text in readme
    assert (ROOT/'CHANGELOG.md').exists()
    assert (ROOT/'docs/hook-coexistence.md').exists()

def test_feedback_unused_locals_removed():
    text=(ROOT/'scripts/domain_feedback.mjs').read_text()
    for name in ['name','input','command']:
        assert f'const {name}=' not in text

@pytest.mark.parametrize('command',['close','verify'])
def test_case_reads_each_evidence_once(tmp_path, command):
    evidence=tmp_path/'evidence'; evidence.mkdir(); sample=evidence/'disk.bin'; sample.write_bytes(b'original')
    custody=tmp_path/'case/custody'; custody.mkdir(parents=True)
    import hashlib
    (custody/'hashes-start.json').write_text(json.dumps({'evidencePath':str(evidence),'files':[{'path':str(sample),'sha256':hashlib.sha256(b'original').hexdigest()}]}))
    (custody/'log.jsonl').write_text(json.dumps({'type':'init','evidencePath':str(evidence)})+'\n')  # close requires the intake record
    probe=tmp_path/'probe.mjs'
    probe.write_text("import fs from 'node:fs'; const original=fs.createReadStream; fs.createReadStream=function(p,...a){console.error('EVIDENCE_READ');return original.call(this,p,...a)};")
    result=subprocess.run(['node','--import',str(probe),str(ROOT/'scripts/case_mode.mjs'),command,'--case',str(custody.parent)],text=True,capture_output=True)
    assert result.returncode==0,result.stderr
    assert result.stderr.count('EVIDENCE_READ')==1

def test_hash_rejects_change_during_read(tmp_path):
    sample=tmp_path/'disk.bin'; sample.write_bytes(b'original')
    code="""import fs from 'node:fs';
import {hashEvidence} from './scripts/case_mode.mjs';
const orig=fs.createReadStream; fs.createReadStream=function(p,...args){ const s=orig.call(this,p,...args); s.once('data',()=>fs.appendFileSync(p,'changed')); return s; };
try {await hashEvidence([process.argv[1]]);process.exitCode=1;} catch(e){if(!/changed during hashing/.test(e.message))throw e;}
"""
    result=subprocess.run(['node','--input-type=module','-e',code,str(sample)],cwd=ROOT,text=True,capture_output=True)
    assert result.returncode==0,result.stderr

def test_windows_relative_path_resolution_normalizes_separators(monkeypatch):
    import evidence_output
    from types import SimpleNamespace
    # Emulate pathlib's Windows resolution on this host; no boundary logic stub.
    monkeypatch.setattr(evidence_output,'Path',lambda p: SimpleNamespace(resolve=lambda: 'C:\\case\\'+str(p).replace('/','\\')))
    assert evidence_output.within('evidence/report.json','evidence')
