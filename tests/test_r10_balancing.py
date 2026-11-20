"""Round 10 concrete workspace regressions; no network or external engines."""
import json
import subprocess
import sys
from pathlib import Path
import pytest
from test_r6_workspace import ctx, run, event, batch, rows, ROOT
from test_r9_workspace import js

@pytest.mark.parametrize('command', [
 'sha256sum evidence/chat.txt', 'grep -o 계약금 evidence/chat.txt',
 'sort -t , -k2 reports/x.csv', 'git status', 'ls',
 'lazyforensic manifest evidence --verify m.json',
 'lazyforensic verify reports/r.md --evidence m.json',
 'lazyforensic scan evidence --markdown reports/survey.md',
 'lazyforensic pii evidence/chat.txt', 'lazyothers stamp evidence/contract.pdf',
 'node scripts/case_mode.mjs init evidence --out ../case',
 'python3 skills/forensic-audit/scripts/audit_timestamps.py evidence/chat.txt --json > audit.json',
 'node report-tools.mjs claims snapshot --from S3=evidence/chat.txt --session-dir reports/research',
 'exiftool -j -G evidence/a.jpg',
])
def test_r10_read_semantics(ctx,command):
    p=run('evidence_guard.mjs',event(ctx,{'command':command},'exec_command'),'pre-tool-use')
    assert p.returncode==0,p.stderr

@pytest.mark.parametrize('command', [
 'exiftool -XMP:Comment=pwn evidence/photo.jpg',
 'exiftool -Comment+=pwn evidence/photo.jpg',
 'exiftool "-DateTimeOriginal-=1:0:0" evidence/photo.jpg',
 'exiftool -geotag /tmp/t.gpx evidence/photo.jpg',
 'exiftool -@ /tmp/args.txt evidence/photo.jpg',
 'tar -xf /tmp/a.tar --directory=evidence',
 'git --work-tree=evidence checkout HEAD -- .',
 'lazyforensic manifest evidence -o evidence/m.json',
 'lazyforensic pii evidence/a.txt --mask',
 'node report-tools.mjs claims snapshot --from S3=input.txt --session-dir evidence/x',
])
def test_r10_write_denied(ctx,command):
    assert run('evidence_guard.mjs',event(ctx,{'command':command},'exec_command'),'pre-tool-use').returncode==1

def test_r10_patch_text(ctx):
    assert run('evidence_guard.mjs',event(ctx,{'patchText':'*** Delete File: evidence/chat.txt'},'apply_patch'),'pre-tool-use').returncode==1

@pytest.mark.parametrize('command',['sha256sum evidence/chat.txt','git status','ls','grep -rn 계약금 evidence','grep -o 계약금 evidence/chat.txt','sort -t , -k2 reports/x.csv','exiftool -j evidence/photo.jpg'])
def test_r10_read_relay(ctx,command):
    batch(event(ctx,{'command':command},'run_command'))
    assert rows(ctx)==[]

@pytest.mark.parametrize('name,args',[('mcp__github__get_issue',{}),('call_mcp_tool',{'tool':'search_code'}),('mcp__memory__read_graph',{})])
def test_r10_mcp_read_relay(ctx,name,args):
    batch(event(ctx,args,name));assert rows(ctx)==[]

def test_r10_unknown_verdict():
    values=js("import {classifyGuardResult as c} from './scripts/guard_verdict.mjs'; console.log(JSON.stringify(['','{}','broken','null','[]'].map(stdout=>c({status:0,stdout}))));")
    assert all(v['kind']=='unchecked' for v in values)

def test_r10_hooks_registered():
    hooks=json.loads((ROOT/'hooks.json').read_text())['hooks']
    for phase in ['PreToolUse','PostToolUse']:
        for name in ['exec_command','search_update','apply_patch','write_file','run_command','mcp__kordoc__redact_document']:
            assert js('console.log(JSON.stringify('+json.dumps([h['matcher'] for h in hooks[phase]])+'.some(r=>new RegExp(r).test('+json.dumps(name)+'))));')

def test_r10_case_overlap(ctx):
    evidence=ctx/'input';evidence.mkdir();(evidence/'a.txt').write_text('original')
    p=subprocess.run(['node',str(ROOT/'scripts/case_mode.mjs'),'init',str(evidence),'--out',str(evidence/'case')],capture_output=True,text=True)
    assert p.returncode!=0 and not (evidence/'case').exists()

def test_r10_single_evidence(ctx):
    evidence=ctx/'disk.E01';evidence.write_bytes(b'EVF\t\r\n\xff\0')
    case=ctx/'case'
    p=subprocess.run(['node',str(ROOT/'scripts/case_mode.mjs'),'init',str(evidence),'--out',str(case)],capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    assert run('evidence_guard.mjs',event(case,{'path':'reports/report.md'}),'pre-tool-use').returncode==0
    assert run('evidence_guard.mjs',event(case,{'path':str(evidence)}),'pre-tool-use').returncode==1

@pytest.mark.parametrize('value',['M123A4567','+82 31 123 4567','02.123.4567','주민등록번호: 9001011234567','외국인등록번호: 9001015123456','계좌번호: 110123456789'])
def test_r10_shared_pii(value):
    sys.path.insert(0,str(ROOT/'scripts'));import pii_mask,mask_korean_pii
    assert pii_mask.mask_text(value)!=value
    assert mask_korean_pii.mask_text(value,mask_korean_pii.ALL_TYPES)[0]!=value

def test_r10_encoding_and_zero_output(ctx):
    sys.path.insert(0,str(ROOT/'scripts'));import pii_mask
    source=ctx/'input.txt';dest=ctx/'output.txt'
    source.write_bytes('성명: 김철수'.encode('cp949'));dest.write_text('stale')
    result=pii_mask.process_file(source,True,dest,False)
    assert 'error' not in result
    assert dest.read_bytes().decode('cp949')=='성명: 김철수'

@pytest.mark.parametrize('name',['inventory.csv','notes.md'])
def test_r10_file_header_text(ctx,name):
    p=ctx/name;p.write_text('FILENAME,SIZE,SHA256\nFILE 목록')
    assert run('evidence_guard.mjs',event(ctx,{'path':str(p)}),'pre-tool-use').returncode==0

def test_r10_directory_copy(ctx):
    (ctx/'reports').mkdir()
    payload=event(ctx,{'command':'cp "draft one.md" two.md reports/'},'run_command')
    result=js("import {contentTargets} from './scripts/hook_targets.mjs';console.log(JSON.stringify(contentTargets([{parsed:"+json.dumps(payload)+"}])));")
    assert set(result)=={str(ctx/'reports/draft one.md'),str(ctx/'reports/two.md')}

def test_r10_lock_abort(ctx):
    target=ctx/'a.txt';target.write_text('a')
    lock=ctx/'.lazyneon-workspace/audit_trail.jsonl.lock';lock.mkdir(parents=True)
    p=run('evidence_guard.mjs',event(ctx,{'path':str(target)}),'post-tool-use',env={'LAZYNEON_WS_SINGLE_TARGET':'1'})
    assert p.returncode!=0 and 'NOT_CHECKED' in p.stdout
    assert not lock.with_name('audit_trail.jsonl').exists()
    assert lock.exists()

def test_r10_no_core_registry_read(ctx):
    result=js("import fs from 'node:fs';import {evidenceIdentity} from './scripts/evidence_identity.mjs';const calls=[];const read=fs.readdirSync;fs.readdirSync=(p,...a)=>{calls.push(p);return read(p,...a)};evidenceIdentity("+json.dumps(str(ctx))+");console.log(JSON.stringify(calls));")
    assert str(ctx/'.lazyneon') not in result

def test_r10_manifest_grounding(ctx):
    sys.path.insert(0,str(ROOT/'scripts'));from report_core import verified_evidence_text
    import hashlib
    source=ctx/'a.txt';source.write_text('original');digest=hashlib.sha256(source.read_bytes()).hexdigest()
    manifest=ctx/'m.json';doc={'manifest_version':1,'root':str(ctx),'files':[{'path':'a.txt','sha256':digest}]};manifest.write_text(json.dumps(doc))
    assert digest in verified_evidence_text(manifest)
    doc['files'][0]['sha256']='a'*64;manifest.write_text(json.dumps(doc))
    with pytest.raises(ValueError):verified_evidence_text(manifest)

@pytest.mark.parametrize('kind',['file','directory'])
def test_r10_nested_symlink(ctx,kind):
    source=ctx/'input';source.mkdir();target=ctx/'target'
    if kind=='directory': target.mkdir();(target/'a').write_text('a')
    else:target.write_text('a')
    (source/'link').symlink_to(target,target_is_directory=kind=='directory')
    p=subprocess.run(['node',str(ROOT/'scripts/case_mode.mjs'),'init',str(source),'--out',str(ctx/'case')],capture_output=True,text=True)
    assert p.returncode!=0 and 'Symlink' in p.stderr and not (ctx/'case').exists()

def test_r10_pii_read_error(ctx,monkeypatch,capsys):
    sys.path.insert(0,str(ROOT/'scripts'));import pii_mask
    source=ctx/'a.txt';source.write_text('a')
    def fail(*a,**kw):raise PermissionError('blocked')
    monkeypatch.setattr(Path,'read_bytes',fail)
    assert pii_mask.main([str(source)])==2
    assert '미탐지' not in capsys.readouterr().out

def test_r10_download_default(monkeypatch):
    sys.path.insert(0,str(ROOT/'scripts'));import local_ocr,local_stt
    import types
    calls=[]
    monkeypatch.setitem(sys.modules,'easyocr',types.SimpleNamespace(Reader=lambda *a,**kw:calls.append(kw)))
    local_ocr._EASYOCR_READER_CACHE.clear()
    local_ocr._get_easyocr_reader(['ko'])
    assert calls[-1]['download_enabled'] is False

@pytest.mark.parametrize('offline_key',['LAZYNEON_OFFLINE','LAZYNEON_WS_OFFLINE','LAZYNEON_WS'])
def test_r10_download_consent_and_offline(ctx,monkeypatch,offline_key):
    sys.path.insert(0,str(ROOT/'scripts'));import model_download_policy as policy
    for key in ['LAZYNEON_OFFLINE','LAZYNEON_WS_OFFLINE','LAZYNEON_WS']:monkeypatch.delenv(key,raising=False)
    assert not policy.downloads_allowed(False)
    assert policy.downloads_allowed(True)
    monkeypatch.setenv(offline_key,'{"offline":true}' if offline_key=='LAZYNEON_WS' else '1')
    assert not policy.downloads_allowed(True)
    with pytest.raises(PermissionError):policy.local_model_or_consent('missing-model',True)
    local=ctx/'model';local.mkdir();assert policy.local_model_or_consent(str(local),True)==str(local)

def test_r10_whisper_local_only(monkeypatch):
    sys.path.insert(0,str(ROOT/'scripts'));import local_stt,types
    calls=[]
    class Model:
        def __init__(self,*a,**kw):calls.append(kw)
        def transcribe(self,*a,**kw):return [],None
    monkeypatch.setitem(sys.modules,'faster_whisper',types.SimpleNamespace(WhisperModel=Model))
    local_stt._WHISPER_MODEL_CACHE.clear()
    local_stt.transcribe_faster_whisper(Path('x.wav'),'ko',False,'tiny')
    assert calls==[{'local_files_only':True}]

@pytest.mark.parametrize('kind',['NFD','uppercase'])
def test_r10_path_identity(ctx,kind):
    import unicodedata
    root=ctx/('증거' if kind=='NFD' else 'Originals');root.mkdir();(root/'a.txt').write_text('original')
    (ctx/'manifest.json').write_text(json.dumps({'manifest_version':1,'root':str(root),'files':[{'path':'a.txt'}]}))
    alias=unicodedata.normalize('NFD',str(root)) if kind=='NFD' else str(root.with_name('ORIGINALS'))
    for args,name in [({'command':f'cp x "{alias}/new.txt"'},'run_command'),({'command':f'rm "{alias}/a.txt"'},'run_command'),({'path':alias+'/a.txt'},'write_file')]:
        # Native alias spelling only aliases the original on insensitive filesystems.
        if Path(alias).exists():assert run('evidence_guard.mjs',event(ctx,args,name),'pre-tool-use').returncode==1
    assert run('evidence_guard.mjs',event(ctx,{'path':str(ctx/'outside/a.txt')}),'pre-tool-use').returncode==0

@pytest.mark.parametrize('name',['brief.md','claim-graph.md','intent-diff.md','observation-manifest.md','verification-economics.md','cause-disappearance.md','excursion-log.md','expansion-log.md','sources-ledger.md','debate-log.md'])
def test_r10_core_journal(ctx,name):
    target=ctx/'.lazyneon/ulw-research/session'/name;target.parent.mkdir(parents=True);target.write_text('민법 제1500조')
    batch(event(ctx,{'path':str(target)}))
    assert rows(ctx)==[] and not (ctx/'.lazyneon-workspace/audit_trail.jsonl').exists()

def test_r10_required_module(monkeypatch,capsys):
    sys.path.insert(0,str(ROOT/'scripts'));import setup_forensic_env as setup
    monkeypatch.setattr(setup,'check_environment',lambda:{'python':'3.12','modules':{'kiwipiepy':False,'easyocr':False},'binaries':{}})
    assert setup.main(['--check'])==2
    assert 'required module kiwipiepy' in capsys.readouterr().out
    monkeypatch.setattr(setup,'check_environment',lambda:{'python':'3.12','modules':{'kiwipiepy':True,'easyocr':False},'binaries':{}})
    assert setup.main(['--check'])==0

def test_r10_local_media_example():
    text=(ROOT/'skills/media-analysis/SKILL.md').read_text()
    assert '--upload-audio' not in text.split('```')[1]
    assert '이번 파일' in text and '명시적으로 동의' in text

def test_r10_timestamp_output(ctx):
    p=ctx/'input';p.write_text('original');out=ctx/'audit.json'
    proc=subprocess.run([sys.executable,str(ROOT/'skills/forensic-audit/scripts/audit_timestamps.py'),str(p),'-o',str(out),'--json'],text=True,capture_output=True)
    assert proc.returncode==0,proc.stderr
    assert json.loads(out.read_text())['sha256']==json.loads(proc.stdout)['sha256']
    assert p.read_text()=='original'

@pytest.mark.parametrize('name',['exec_command','search_update'])
def test_r10_real_hook_dispatch(ctx,name):
    from test_r6_oracle_workspace import dispatch
    args={'command':'echo changed > evidence/chat.txt'} if name=='exec_command' else {'file_path':'evidence/chat.txt'}
    assert dispatch('PreToolUse',event(ctx,args,name))[0].returncode==1
    target=ctx/'소장.md';target.write_text('민법 제1500조')
    args={'command':'cp input.md 소장.md'} if name=='exec_command' else {'file_path':str(target)}
    dispatch('PostToolUse',event(ctx,args,name))
    assert any(r['guard']=='legal_factuality_guard.mjs' and r['kind']=='fail' for r in rows(ctx))


def test_r10_bind_mixed(ctx,capsys):
    sys.path.insert(0,str(ROOT/'scripts'));import bind_court_pdf as binder
    import fitz
    doc=fitz.open();doc.new_page();pdf=ctx/'a.pdf';doc.save(pdf);doc.close()
    image=ctx/'b.png'
    from PIL import Image
    Image.new('RGB',(10,10)).save(image)
    manifest=ctx/'m.json';manifest.write_text(json.dumps([{'file':str(pdf)},{'file':str(image)}]))
    out=ctx/'bound.pdf'
    assert binder.main(['-i',str(manifest),'-o',str(out)])==2
    assert str(image) in capsys.readouterr().err and not out.exists()
    assert binder.main(['-i',str(manifest),'-o',str(out),'--skip-non-pdf'])==0
    assert str(image) in capsys.readouterr().err
    with fitz.open(out) as result:assert len(result)==1


def test_r10_audit_concurrent(ctx):
    from concurrent.futures import ThreadPoolExecutor
    import hashlib
    target=ctx/'a.txt';target.write_text('original')
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(lambda _:run('evidence_guard.mjs',event(ctx,{'path':str(target)}),'post-tool-use',env={'LAZYNEON_WS_SINGLE_TARGET':'1'}),range(12)))
    assert all(r.returncode==0 and json.loads(r.stdout)['status']=='PASS' for r in results)
    previous=None;lines=(ctx/'.lazyneon-workspace/audit_trail.jsonl').read_text().splitlines()
    assert len(lines)==12
    for line in lines:
        row=json.loads(line);assert row['prev_hash']==previous
        previous=hashlib.sha256(line.encode()).hexdigest()


def test_r10_report_hook_manifest(ctx):
    import hashlib
    source=ctx/'input.txt';source.write_text('original')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    (ctx/'manifest.json').write_text(json.dumps({'manifest_version':1,'root':str(ctx),'files':[{'path':'input.txt','sha256':digest}]}))
    # Only the unavailable tokenizer is substituted; actual report/hash validators run.
    stub=ctx/'pythonpath';stub.mkdir()
    (stub/'kiwipiepy.py').write_text('class Kiwi:\n def add_user_word(self,*a): pass\n def tokenize(self,text): return []\n')
    report=ctx/'report.md';report.write_text('input.txt SHA-256: '+digest)
    env={'PYTHONPATH':str(stub),'LAZYNEON_WS_SINGLE_TARGET':'1'}
    good=run('hallucination_guard.mjs',event(ctx,{'path':str(report)}),env=env)
    assert good.returncode==0 and json.loads(good.stdout)['status']=='PASS',good.stderr+good.stdout
    report.write_text('input.txt SHA-256: '+'a'*64)
    bad=run('hallucination_guard.mjs',event(ctx,{'path':str(report)}),env=env)
    assert bad.returncode==1 and json.loads(bad.stdout)['decision']=='block'


def test_r10_symlink_cli_failure_detected(ctx):
    script=ctx/'bad.mjs';script.write_text('this is not javascript')
    result=subprocess.run(['node',str(script),'--help'],text=True,capture_output=True)
    def validate(p):
        assert p.returncode==0
        assert 'Usage:' in p.stdout+p.stderr
    with pytest.raises(AssertionError):validate(result)
    good=subprocess.run(['node',str(ROOT/'scripts/case_mode.mjs'),'--help'],text=True,capture_output=True)
    validate(good)


def test_r10_matcher_mutation_detected():
    import re
    def check(matcher):
        assert all(re.search(matcher,name) for name in ['exec_command','search_update','apply_patch','write_file'])
    for phase in ['PreToolUse','PostToolUse']:check(json.loads((ROOT/'hooks.json').read_text())['hooks'][phase][0]['matcher'])
    with pytest.raises(AssertionError):check('^(apply_patch|write_file)$')


def test_r10_windows_wrapper_contract():
    # Actual Windows execution is conditional on the platform, source invariants
    # and their destructive mutations are checked on every platform.
    import os
    cmd=(ROOT/'scripts/py.cmd').read_text();ps=(ROOT/'scripts/py.ps1').read_text()
    def check(c,p):
        assert 'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0py.ps1" %*' in c
        assert 'exit /b %ERRORLEVEL%' in c
        assert '& $Py @args' in p and 'exit $LASTEXITCODE' in p
        assert '$env:LAZYNEON_WS_PYTHON' in p
    check(cmd,ps)
    for c,p in [(cmd.replace('%*',''),ps),(cmd,ps.replace('& $Py @args','')),(cmd.replace('exit /b %ERRORLEVEL%','exit /b 0'),ps)]:
        with pytest.raises(AssertionError):check(c,p)
    if os.name=='nt':
        result=subprocess.run([str(ROOT/'scripts/py.cmd'),'-c','import sys;sys.exit(7)'],env={**os.environ,'LAZYNEON_WS_PYTHON':sys.executable})
        assert result.returncode==7


def test_r10_case_display_and_settings(ctx):
    import datetime
    for ext in ['E01','E02']:(ctx/f'disk.{ext}').write_text('segment')
    p=subprocess.run(['node',str(ROOT/'scripts/case_mode.mjs'),'init',str(ctx/'disk.E01')],cwd=ctx,text=True,capture_output=True)
    assert p.returncode==0 and '../disk.E02' not in p.stdout
    case=next(ctx.glob('case-*'))
    assert case.name.endswith(datetime.datetime.now().astimezone().strftime('%z'))
    settings=case/'.lazyneon-workspace/case-settings.json';before=settings.read_bytes()
    repeat=subprocess.run(['node',str(ROOT/'scripts/case_mode.mjs'),'init',str(ctx/'disk.E01'),'--out',str(case)],text=True,capture_output=True)
    assert repeat.returncode!=0 and settings.read_bytes()==before

@pytest.mark.parametrize('name',['mcp__kordoc__parse_document','read_file'])
def test_r10_read_tool_output_boundary(ctx,name):
    assert run('evidence_guard.mjs',event(ctx,{'path':'evidence/a.pdf'},name),'pre-tool-use').returncode==0
    assert run('evidence_guard.mjs',event(ctx,{'path':'evidence/a.pdf','output_path':'evidence/output.txt'},name),'pre-tool-use').returncode==1

@pytest.mark.parametrize('command',[
 'python3 -c "open(\'evidence/a.txt\',\'w\').write(\'x\')"',
 'node -e "require(\'fs\').writeFileSync(\'evidence/a.txt\',\'x\')"',
 'python3 -c "from pathlib import Path;Path(\'evidence/a.txt\').write_text(\'x\')"',
 'cp a.txt b.txt evidence/', 'mv evidence/a.txt reports/a.txt', 'chmod 600 evidence/a.txt',
 'dd if=a.txt of=evidence/a.txt', 'rsync a.txt evidence/',
])
def test_r10_write_semantics_regressions(ctx,command):
    assert run('evidence_guard.mjs',event(ctx,{'command':command},'exec_command'),'pre-tool-use').returncode==1

@pytest.mark.parametrize('command',['sha256sum evidence/chat.txt 2>&1','rm reports/old.md','chmod 600 reports/a.md'])
def test_r10_noncontent_relay(ctx,command):
    batch(event(ctx,{'command':command},'exec_command'));assert rows(ctx)==[]

@pytest.mark.parametrize('command',[
 'python3 -c "open(\'evidence/a.txt\',\'r+\')"',
 'python3 -c "open(\'evidence/a.txt\',mode=\'w\')"',
 'python3 -c "from pathlib import Path;Path(\'evidence/a.txt\').open(\'w\')"',
 'python3 -c "import os;os.rename(\'outside.txt\',\'evidence/a.txt\')"',
 "python3 - <<'EOF'\nopen('evidence/a.txt','w').write('x')\nEOF",
])
def test_r10_interpreter_write_modes(ctx,command):
    assert run('evidence_guard.mjs',event(ctx,{'command':command},'exec_command'),'pre-tool-use').returncode==1

@pytest.mark.parametrize('command',['exiftool -orientation -j evidence/a.jpg','python3 -c "print(open(\'evidence/a.txt\',\'r\').read())"'])
def test_r10_read_flags(ctx,command):
    # R11 requires an explicit read program; arbitrary inline interpreters are denied.
    expected = 1 if command.startswith('python3 -c') else 0
    assert run('evidence_guard.mjs',event(ctx,{'command':command},'exec_command'),'pre-tool-use').returncode==expected
    batch(event(ctx,{'command':command},'exec_command'));assert rows(ctx)==[]


def test_r10_unknown_script_policy(ctx):
    batch(event(ctx,{'command':'python gen.py'},'exec_command'))
    assert len(rows(ctx))==1 and rows(ctx)[0]['kind']=='unchecked'
    assert 'PASS' not in rows(ctx)[0]['message']


def test_r10_structural_signature(ctx):
    import struct
    target=ctx/'record.bin';record=bytearray(1024);record[:4]=b'FILE'
    struct.pack_into('<H',record,4,48);struct.pack_into('<H',record,20,56);target.write_bytes(record)
    assert run('evidence_guard.mjs',event(ctx,{'path':str(target)}),'pre-tool-use').returncode==1
    target.write_text('FILE 목록')
    assert run('evidence_guard.mjs',event(ctx,{'path':str(target)}),'pre-tool-use').returncode==0

@pytest.mark.parametrize('kind',['file','directory'])
def test_r10_evidence_link_referent_protected(ctx,kind):
    evidence=ctx/'evidence';evidence.mkdir();outside=ctx/'outside'
    if kind=='directory':outside.mkdir();target=outside/'a.txt';target.write_text('original')
    else:outside.write_text('original');target=outside
    (evidence/'link').symlink_to(outside,target_is_directory=kind=='directory')
    assert run('evidence_guard.mjs',event(ctx,{'path':str(target)}),'pre-tool-use').returncode==1
    assert run('evidence_guard.mjs',event(ctx,{'path':str(ctx/'report.md')}),'pre-tool-use').returncode==0

@pytest.mark.parametrize('alias',['custody','.lazyneon-workspace'])
def test_r10_case_output_alias(ctx,alias):
    evidence=ctx/'input';evidence.mkdir();(evidence/'a').write_text('original')
    case=ctx/'case';case.mkdir();(case/alias).symlink_to(evidence,target_is_directory=True)
    before=set(evidence.iterdir())
    p=subprocess.run(['node',str(ROOT/'scripts/case_mode.mjs'),'init',str(evidence),'--out',str(case)],text=True,capture_output=True)
    assert p.returncode!=0 and set(evidence.iterdir())==before


def test_r10_existing_settings(ctx):
    source=ctx/'a';source.write_text('a');case=ctx/'case'
    settings=case/'.lazyneon-workspace/case-settings.json';settings.parent.mkdir(parents=True);settings.write_text('owner settings')
    p=subprocess.run(['node',str(ROOT/'scripts/case_mode.mjs'),'init',str(source),'--out',str(case)],text=True,capture_output=True)
    assert p.returncode!=0 and settings.read_text()=='owner settings'
    assert not (case/'custody').exists()


def test_r10_unlisted_read_mcp(ctx):
    payload=event(ctx,{'path':'evidence/input.txt'},'mcp__docs__lookup_document')
    assert run('evidence_guard.mjs',payload,'pre-tool-use').returncode==0
    batch(payload);assert rows(ctx)==[]


def test_r10_case_existing_log_link(ctx):
    source=ctx/'input';source.write_text('immutable');case=ctx/'case';(case/'custody').mkdir(parents=True)
    (case/'custody/log.jsonl').symlink_to(source)
    p=subprocess.run(['node',str(ROOT/'scripts/case_mode.mjs'),'init',str(source),'--out',str(case)],capture_output=True,text=True)
    assert p.returncode!=0 and source.read_text()=='immutable'
    assert not (case/'custody/hashes-start.json').exists()


def test_r10_pii_directory_write_boundary(ctx):
    evidence=ctx/'증거';evidence.mkdir();(evidence/'a.txt').write_text('010-1234-5678')
    (ctx/'manifest.json').write_text(json.dumps({'manifest_version':1,'root':str(evidence),'files':[]}))
    for command in ['lazyforensic pii 증거 --mask',f'python3 {ROOT}/scripts/pii_mask.py 증거/a.txt --mask', 'lazyforensic pii 증거/a.txt --mask --in-place -o reports/a.txt']:
        assert run('evidence_guard.mjs',event(ctx,{'command':command},'exec_command'),'pre-tool-use').returncode==1
    assert run('evidence_guard.mjs',event(ctx,{'command':'lazyforensic pii 증거/a.txt --mask -o reports/a.txt'},'exec_command'),'pre-tool-use').returncode==0


def test_r10_ffmpeg_option_roles(ctx):
    payload=event(ctx,{'command':'ffmpeg -i in.mp4 -t 30 reports/clip.mp4'},'exec_command')
    result=js("import {contentTargets} from './scripts/hook_targets.mjs';console.log(JSON.stringify(contentTargets([{parsed:"+json.dumps(payload)+"}])));")
    assert result==[str(ctx/'reports/clip.mp4')]

@pytest.mark.parametrize('engine',['openai','sensevoice','moonshine'])
def test_r10_other_models_offline_and_local(ctx,monkeypatch,engine):
    sys.path.insert(0,str(ROOT/'scripts'));import local_stt,types
    calls=[]
    class Model:
        def transcribe(self,*a,**kw):return {'segments':[]}
        def generate(self,*a,**kw):return []
    def load(*a,**kw):calls.append((a,kw));return Model()
    monkeypatch.setitem(sys.modules,'whisper',types.SimpleNamespace(load_model=load))
    monkeypatch.setitem(sys.modules,'funasr',types.SimpleNamespace(AutoModel=load))
    monkeypatch.setitem(sys.modules,'funasr.utils.postprocess_utils',types.SimpleNamespace(rich_transcription_postprocess=lambda text:text))
    monkeypatch.setitem(sys.modules,'moonshine',types.SimpleNamespace(transcribe=lambda *a:(calls.append(a) or [])))
    monkeypatch.setattr(local_stt,'_ALLOW_MODEL_DOWNLOAD',True,raising=False)
    monkeypatch.setenv('XDG_CACHE_HOME',str(ctx/'cache'))
    def transcribe(model):
        if engine=='openai':return local_stt.transcribe_openai_whisper(Path('a.wav'),'ko',False,model)
        if engine=='sensevoice':return local_stt.transcribe_sensevoice(Path('a.wav'),'ko',model)
        return local_stt.transcribe_moonshine(Path('a.wav'),model)
    with pytest.raises(PermissionError):transcribe('missing-r10-model')
    assert calls==[]
    local=ctx/'model.pt';local.write_bytes(b'local fixture')
    assert transcribe(str(local))['segments']==[] and len(calls)==1
