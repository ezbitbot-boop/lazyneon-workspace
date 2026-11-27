"""R12 regressions: all OS mutations confined to temporary directories."""
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from test_r6_workspace import ctx, run, event, ROOT
from conftest import release_tree
from test_r11_workspace import case

READS = [
    *[f'lazyforensic {sub} evidence/a' for sub in 'dedup similar kw archive pdf db vcheck vfp afp video deepfake mft telegram'.split()],
    *[f'lazyothers {sub} evidence/a' for sub in 'doc ruling flow db integrity certify morph'.split()],
    'ls -lO evidence/a', 'iconv -f cp949 -t utf8 evidence/a',
    'cat evidence/a | sort | uniq -c', 'cut -f 1 evidence/a',
    'tesseract evidence/a stdout -l kor+eng', 'ffmpeg -i evidence/a -t 0.5 clip.wav',
    'cp evidence/a work.txt', 'lazyforensic sig evidence/a && lazyforensic timestamps evidence/a',
    'type evidence/a', 'dir evidence/a', 'findstr /I word evidence/a', 'more evidence/a',
    'certutil -hashfile evidence/a SHA256', 'Get-Content evidence/a -Encoding UTF8',
    'Get-Acl evidence/a', 'icacls evidence/a', 'attrib evidence/a',
    f'python3 {ROOT}/scripts/local_ocr.py evidence/a --engine easyocr',
    f'python3 {ROOT}/scripts/local_ocr.py evidence/a --engine easyocr --out ocr.json',
]
@pytest.mark.parametrize('command', READS)
def test_r12_documented_reads(ctx, command):
    r=run('evidence_guard.mjs',event(ctx,{'command':command},'exec_command'),'pre-tool-use')
    assert r.returncode==0, r.stdout+r.stderr

@pytest.mark.parametrize('command', READS)
def test_r12_reads_cannot_redirect_into_evidence(ctx, command):
    r=run('evidence_guard.mjs',event(ctx,{'command':command+' > evidence/result'},'exec_command'),'pre-tool-use')
    assert r.returncode==1, r.stdout+r.stderr

@pytest.mark.parametrize('output', [False,True])
def test_r12_manifest_is_observational(ctx, output):
    evidence=ctx/'data';evidence.mkdir();f=evidence/'a';f.write_text('a');before=f.stat().st_mode
    try:
        args=[sys.executable,str(ROOT/'scripts/evidence_manifest.py'),str(evidence)]
        if output:args+=['-o',str(ctx/'manifest.json')]
        r=subprocess.run(args,capture_output=True,text=True,cwd=ctx)
        assert r.returncode==0,r.stderr
        assert f.stat().st_mode==before
        assert not getattr(f.stat(),'st_flags',0)&2
        (evidence/'new').write_text('new')
    finally:release_tree(ctx)

def test_r12_large_init_and_durable_journal(ctx):
    evidence=ctx/'data';evidence.mkdir()
    for i in range(4500):(evidence/(str(i)+'x'*80)).write_text('a')
    work=ctx/'work'
    try:
        r=case(ctx,'init',evidence,'--out',work);assert r.returncode==0,r.stderr
        journal=work/'custody/protection.jsonl'
        assert journal.exists()
        assert len(journal.read_text().splitlines())>=4502
        assert case(ctx,'close','--case',work).returncode==0
    finally:release_tree(ctx)

def test_r12_relock_lifecycle(ctx):
    evidence=ctx/'data';evidence.mkdir();(evidence/'a').write_text('a');work=ctx/'work'
    try:
        assert case(ctx,'init',evidence,'--out',work).returncode==0
        assert case(ctx,'unlock','--case',work,'--reason','handover').returncode==0
        r=case(ctx,'lock','--case',work,'--reason','resume');assert r.returncode==0,r.stderr
        r=case(ctx,'close','--case',work);assert r.returncode==0,r.stderr
        assert 'unlock' in r.stdout
        assert case(ctx,'unlock','--case',work,'--reason','done').returncode==0
        (evidence/'a').write_text('b')
    finally:release_tree(ctx)

def test_r12_root_swap_detected(ctx):
    parent=ctx/'parent';parent.mkdir();evidence=parent/'data';evidence.mkdir();(evidence/'a').write_text('a');work=ctx/'work'
    try:
        assert case(ctx,'init',evidence,'--out',work).returncode==0
        parent.rename(ctx/'moved');parent.mkdir();evidence.symlink_to(ctx/'moved/data',target_is_directory=True)
        r=case(ctx,'close','--case',work)
        assert r.returncode==1 and 'identity changed' in r.stderr
    finally:release_tree(ctx)

def test_r12_required_parser_dependency_fails_closed():
    # Test the existing test itself in a child with imports blocked, no installed
    # dependency is removed and production parsing is never mocked successful.
    code="""import sys, importlib.abc, runpy
class Missing(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, *args):
  if fullname in ('olefile','hwp_hwpx_parser'): raise ModuleNotFoundError(fullname)
sys.meta_path.insert(0, Missing())
runpy.run_path('tests/test_hwp5_fixture.py', run_name='dependency_probe')
"""
    # A required dependency check must fail immediately, not become a skip/pass.
    r=subprocess.run([sys.executable,'-c',code],cwd=ROOT,capture_output=True,text=True)
    assert r.returncode!=0

def test_r12_readonly_media_never_mutates(ctx,monkeypatch):
    sys.path.insert(0,str(ROOT/'scripts'));import evidence_protection as ep
    evidence=ctx/'data';evidence.mkdir();(evidence/'a').write_text('a')
    # Simulate the OS volume query, not successful lock calls.
    monkeypatch.setattr(ep,'read_only_media',lambda p:True,raising=False)
    def forbidden(*a,**kw):raise AssertionError('write-blocked media must not be mutated')
    monkeypatch.setattr(Path,'chmod',forbidden)
    record=None
    try:
        record=ep.protect([evidence])
        assert all(e['status']=='protected-by-media' and not e['applied'] for e in record['entries'])
        assert ep.verify(record)==[]
    finally:
        if record is not None:ep.unlock(record)

def test_r12_unsupported_flags_are_honest(ctx,monkeypatch):
    sys.path.insert(0,str(ROOT/'scripts'));import evidence_protection as ep
    evidence=ctx/'data';evidence.mkdir();(evidence/'a').write_text('a')
    # A filesystem can return success without applying mode/flag changes (FAT).
    monkeypatch.setattr(Path,'chmod',lambda *a,**kw:None)
    if hasattr(os,'chflags'):monkeypatch.setattr(os,'chflags',lambda *a:None)
    def silent(*args):
        # Success without effect; Windows protect reads back the ACL it asked icacls to save.
        if args[0]=='icacls' and '/save' in args:Path(args[args.index('/save')+1]).write_bytes(b'')
        return ''
    monkeypatch.setattr(ep,'checked',silent)
    monkeypatch.setattr(ep,'command',lambda *a:subprocess.CompletedProcess(a,1,'','unsupported'))
    try:
        record=ep.protect([evidence])
        assert all(e['status']=='not-lockable' and not e['applied'] for e in record['entries'])
        assert ep.verify(record)==[]
    finally:ep.unlock(record) if 'record' in locals() else None

def test_r12_lock_failure_rolls_back_with_journal(ctx,monkeypatch):
    sys.path.insert(0,str(ROOT/'scripts'));import evidence_protection as ep
    evidence=ctx/'data';evidence.mkdir();f=evidence/'a';f.write_text('a');mode=f.stat().st_mode
    journal=ctx/'journal.jsonl';original=Path.chmod;calls=[]
    def failure(p,value,*a,**kw):
        calls.append(p)
        if p==evidence and value&0o222==0:raise OSError('injected lock failure')
        return original(p,value,*a,**kw)
    monkeypatch.setattr(Path,'chmod',failure)
    try:
        with pytest.raises(OSError,match='injected lock failure'):ep.protect([evidence],journal=journal)
        assert f.stat().st_mode==mode and not getattr(f.stat(),'st_flags',0)&2
        rows=[json.loads(line) for line in journal.read_text().splitlines()]
        assert rows[0]['event']=='prepared' and rows[-1]['event']=='rolled-back'
    finally:release_tree(ctx)

@pytest.mark.parametrize('bad', [False,True])
def test_r12_morph_unavailable_cli_hook_parity(ctx,bad):
    source=ctx/'source.txt';source.write_text('원고는 계약을 체결하였다.')
    report=ctx/'소장.md';report.write_text('민법 제9999조' if bad else '원고는 계약을 체결하였다.')
    stub=ctx/'missing';stub.mkdir();(stub/'kiwipiepy.py').write_text('raise ImportError("required engine absent")')
    env={**os.environ,'PYTHONPATH':str(stub)}
    cli=subprocess.run([sys.executable,str(ROOT/'scripts/verify_legal_factuality.py'),str(report),'--source',str(source),'--morph-grounding','--json'],capture_output=True,text=True,env=env)
    assert cli.returncode==1
    doc=json.loads(cli.stdout)
    assert doc['status']==('FAIL' if bad else 'NOT_CHECKED') and 'MORPH_UNAVAILABLE' in doc['status_codes']
    hook=run('legal_factuality_guard.mjs',event(ctx,{'path':str(report)}),env=env)
    assert hook.returncode==1 and json.loads(hook.stdout)['status']==doc['status']

def test_r12_large_manifest_still_protects(ctx,monkeypatch):
    sys.path.insert(0,str(ROOT/'scripts'));from evidence_output import safe_output
    evidence=ctx/'originals';evidence.mkdir();f=evidence/'a';f.write_text('a')
    (ctx/'manifest.json').write_text(json.dumps({'manifest_version':1,'root':str(evidence),'files':[],'padding':'x'*(17*1024*1024)}))
    monkeypatch.chdir(ctx)
    with pytest.raises(ValueError,match='outside evidence'):safe_output(evidence/'out')
    r=run('evidence_guard.mjs',event(ctx,{'path':str(f),'content':'changed'}),'pre-tool-use')
    assert r.returncode==1

def test_r12_hardlink_manifest_error_no_traceback(ctx):
    evidence=ctx/'data';evidence.mkdir();f=evidence/'a';f.write_text('a');os.link(f,ctx/'alias')
    try:
        r=subprocess.run([sys.executable,str(ROOT/'scripts/evidence_manifest.py'),str(evidence),'--protect','-o',str(ctx/'manifest.json')],capture_output=True,text=True)
        assert r.returncode==2 and 'Hard-linked evidence' in r.stderr and 'Traceback' not in r.stderr
    finally:release_tree(ctx)

def test_r12_manifest_then_init_restores_modes(ctx):
    evidence=ctx/'data';evidence.mkdir();f=evidence/'a';f.write_text('a');mode=f.stat().st_mode;work=ctx/'work'
    try:
        r=subprocess.run([sys.executable,str(ROOT/'scripts/evidence_manifest.py'),str(evidence),'--protect','-o',str(ctx/'manifest.json')],cwd=ctx,capture_output=True,text=True)
        assert r.returncode==0,r.stderr
        assert case(ctx,'init',evidence,'--out',work).returncode==0
        assert case(ctx,'unlock','--case',work,'--reason','done').returncode==0
        assert f.stat().st_mode==mode and not getattr(f.stat(),'st_flags',0)&2
    finally:release_tree(ctx)

def test_r12_legacy_case_close_and_unlock(ctx):
    import hashlib
    evidence=ctx/'data';evidence.mkdir();f=evidence/'a';f.write_text('a');work=ctx/'work';(work/'custody').mkdir(parents=True)
    (work/'custody/hashes-start.json').write_text(json.dumps({'evidencePath':str(evidence),'files':[{'path':str(f),'sha256':hashlib.sha256(b'a').hexdigest()}]}))
    (work/'custody/log.jsonl').write_text(json.dumps({'type':'init','evidencePath':str(evidence)})+'\n')  # close requires the intake record
    r=case(ctx,'close','--case',work);assert r.returncode==0 and '구버전' in r.stderr
    r=case(ctx,'unlock','--case',work,'--reason','done');assert r.returncode!=0 and 'No OS protection record' in r.stderr and 'Traceback' not in r.stderr

# Each documented script path and its read flags is exercised through the hook,
# including the Python form that previously had a separate, incomplete list.
DOCUMENTED = [
 ('scripts/dedup_files.py','dedup','--json --no-similar'),
 ('scripts/image_similarity.py','similar','--json --query evidence/b --threshold 10'),
 ('scripts/keyword_report.py','kw','word --context 2 --json -o out.json'),
 ('scripts/archive_survey.py','archive','--json'),('scripts/pdf_audit.py','pdf','--json'),
 ('scripts/sqlite_survey.py','db','--json --sample messages 2'),
 ('scripts/video_integrity.py','vcheck','--json --no-decode'),
 ('scripts/video_fingerprint.py','vfp','--compare evidence/b --scan evidence --samples 5 --threshold 0.4 --json'),
 ('scripts/audio_fingerprint.py','afp','--compare evidence/b --threshold 0.4 --json'),
 ('skills/forensic-video/scripts/forensic_video_audit.py','video','--json'),
 ('scripts/analyze_deepfake_evidence.py','deepfake','--json --plot-fft work.png -o work.md'),
 ('scripts/parse_ntfs_artifacts.py','mft','--json --artifact prefetch --limit 5'),
 ('skills/telegram-chat-extractor/scripts/parse_telegram.py','telegram','--summary --keyword word --sender who --events-out work.json -o out.json'),
 ('scripts/parse_korean_doc.py','doc','--json --strict --engine auto'),
 ('scripts/analyze_court_ruling.py','ruling','--json --verify --source evidence/b --morph-grounding --high-fidelity --strict -o out.json'),
 ('scripts/trace_financial_flow.py','flow','--window-days 7 --top 20 --ctr-threshold 100 --drain-hours 24 -o out.md'),
 ('scripts/query_evidence_db.py','db','--sql "select 1" --list-schema --keywords word --verify-hits 1 --verify-report evidence/b --export-axiom-counts work --scan-insider-prompts --scan-git-dir evidence --json --format md --limit 5 -o out.md'),
 ('scripts/audit_evidence_integrity.py','integrity','--scan-dir evidence --file evidence/b --report evidence/report --algorithms sha256 --output-json out.json -o out.md'),
 ('scripts/certify_evidence_file.py','certify','--url example --note note --case case --reviewer who --output out.json --output-md out.md'),
 ('scripts/korean_morph_grounding.py','morph','--source evidence/b --target evidence/a --text words --threshold 0.7 --filter-procedural --high-fidelity --old-korean --json'),
 ('scripts/citation_grounding.py','cite','--evidence evidence --format both --strict --max-hash-mb 64'),
]
@pytest.mark.parametrize('script,sub,flags',DOCUMENTED)
def test_r12_documented_script_flags(ctx,script,sub,flags):
    program='lazyothers' if script.startswith('scripts/') and sub in ['doc','ruling','flow','integrity','certify','morph'] or script.endswith('query_evidence_db.py') else 'lazyforensic'
    for command in [f'{program} {sub} evidence/a {flags}',f'python3 "{ROOT/script}" evidence/a {flags}']:
        r=run('evidence_guard.mjs',event(ctx,{'command':command},'exec_command'),'pre-tool-use')
        assert r.returncode==0,(command,r.stdout,r.stderr)
        r=run('evidence_guard.mjs',event(ctx,{'command':command+' > evidence/result'},'exec_command'),'pre-tool-use')
        assert r.returncode==1,(command,r.stdout,r.stderr)

@pytest.mark.parametrize('command',[
 'iconv -f cp949 evidence/a -o evidence/b', 'sort evidence/a -o evidence/b',
 'ffmpeg -i evidence/a evidence/b', 'tesseract evidence/a evidence/b',
 'cp evidence/a evidence/b', 'cp evidence/a work && rm evidence/a',
 'Get-Content evidence/a -Encoding UTF8 | Set-Content evidence/b',
 'lazyforensic deepfake evidence/a --plot-fft evidence/out.png',
 'lazyforensic telegram evidence/a --events-out evidence/out.json',
 'lazyothers certify evidence/a --output-md evidence/out.md',
 'lazyothers db evidence/a --export-axiom-counts evidence/out',
])
def test_r12_read_output_flags_still_denied(ctx,command):
    r=run('evidence_guard.mjs',event(ctx,{'command':command},'exec_command'),'pre-tool-use')
    assert r.returncode==1,r.stdout+r.stderr

@pytest.mark.parametrize('command',[
 'ditto evidence/a work', 'rsync -a evidence/a work',
 'Copy-Item -LiteralPath evidence/a -Destination work',
 r'Get-Content evidence\a -Encoding UTF8', r'cmd /c type evidence\a',
 r'cmd /c dir /A evidence', r'findstr /I word evidence\a',
 'cat evidence/a; sha256sum evidence/a',
])
def test_r12_copy_and_windows_reads(ctx,command):
    r=run('evidence_guard.mjs',event(ctx,{'command':command},'exec_command'),'pre-tool-use')
    assert r.returncode==0,r.stdout+r.stderr

@pytest.mark.parametrize('program',['ditto','rsync -a','Copy-Item -Path'])
def test_r12_copy_destination_denied(ctx,program):
    command=f'{program} work evidence/a'
    r=run('evidence_guard.mjs',event(ctx,{'command':command},'exec_command'),'pre-tool-use')
    assert r.returncode==1,r.stdout+r.stderr

def test_r12_cross_os_is_explicitly_unverified(ctx):
    evidence=ctx/'data';evidence.mkdir();(evidence/'a').write_text('a');work=ctx/'work'
    try:
        assert case(ctx,'init',evidence,'--out',work).returncode==0
        baseline=work/'custody/hashes-start.json';doc=json.loads(baseline.read_text());doc['protection']['platform']='foreign-os';baseline.write_text(json.dumps(doc))
        r=case(ctx,'close','--case',work);assert r.returncode==0 and '보호 미검증' in r.stderr
        r=case(ctx,'unlock','--case',work,'--reason','handover');assert r.returncode!=0 and 'recorded OS' in r.stderr and 'Traceback' not in r.stderr
    finally:release_tree(ctx)

def test_r12_runtime_uses_interpreter_candidates(ctx,monkeypatch):
    # Legacy explicit interpreter is part of the existing runtime contract.
    monkeypatch.delenv('LAZYNEON_WS_PYTHON',raising=False)
    monkeypatch.setenv('LAZYNEON_WS_LEGACY_PYTHON',str(ctx/'missing-python'))
    evidence=ctx/'data';evidence.mkdir();(evidence/'a').write_text('a')
    try:
        r=case(ctx,'init',evidence,'--out',ctx/'work')
        assert r.returncode!=0 and 'Python 3 unavailable' in r.stderr
    finally:release_tree(ctx)

def test_r12_interrupted_lock_journal_can_unlock(ctx):
    evidence=ctx/'data';evidence.mkdir();f=evidence/'a';f.write_text('a');mode=f.stat().st_mode
    journal=ctx/'protection.jsonl'
    code="""import sys,os
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import evidence_protection as ep
original=Path.chmod
def crash(p,mode,*a,**kw):
 original(p,mode,*a,**kw)
 os._exit(7)
Path.chmod=crash
ep.protect([sys.argv[2]],journal=sys.argv[3])
"""
    try:
        r=subprocess.run([sys.executable,'-c',code,str(ROOT/'scripts'),str(evidence),str(journal)],cwd=ctx,capture_output=True,text=True)
        assert r.returncode==7 and f.stat().st_mode!=mode
        r=case(ctx,'unlock','--journal',journal,'--reason','interrupted init recovery')
        assert r.returncode==0,r.stderr
        assert f.stat().st_mode==mode
    finally:release_tree(ctx)

@pytest.mark.parametrize('valid_hash',[False,True])
def test_r12_artifact_header_does_not_exempt_hashes(ctx,valid_hash):
    import hashlib
    f=ctx/'source.bin';f.write_bytes(b'actual evidence');digest=hashlib.sha256(f.read_bytes()).hexdigest()
    (ctx/'manifest.json').write_text(json.dumps({'manifest_version':1,'root':str(ctx),'files':[{'path':f.name,'sha256':digest}]}))
    body='증거 source.bin SHA-256: '+(digest if valid_hash else 'a'*64)+'\n'
    marker='<!-- lazyneon-artifact:v1 kind=non-report generator=case_survey sha256='+hashlib.sha256(body.encode()).hexdigest()+' -->\n'
    report=ctx/'generated.md';report.write_text(marker+body)
    r=run('hallucination_guard.mjs',event(ctx,{'path':str(report)}))
    assert r.returncode==(0 if valid_hash else 1),r.stderr
    assert json.loads(r.stdout)['status']==('NOT_APPLICABLE' if valid_hash else 'FAIL')

def test_r12_morph_low_score_is_failure(monkeypatch):
    import scripts.korean_morph_grounding as morph
    import scripts.verify_legal_factuality as legal
    monkeypatch.setattr(morph,'get_kiwi_instance',lambda:object())
    monkeypatch.setattr(morph,'calculate_grounding_overlap',lambda *a,**kw:{'is_grounded':False,'grounding_score':0.1,'unsupported_terms':['조작']})
    result=legal.verify_legal_text('조작 내용',source_text='원본 내용',morph_grounding=True)
    assert result['verdict']=='FAIL' and any('형태소 그라운딩 미달' in e for e in result['errors'])

def test_r12_unprotected_hardlink_manifest_is_readonly(ctx):
    evidence=ctx/'data';evidence.mkdir();f=evidence/'a';f.write_text('a');os.link(f,ctx/'alias');mode=f.stat().st_mode
    try:
        r=subprocess.run([sys.executable,str(ROOT/'scripts/evidence_manifest.py'),str(evidence),'-o',str(ctx/'manifest.json')],capture_output=True,text=True)
        assert r.returncode==0 and 'Traceback' not in r.stderr,r.stderr
        assert f.stat().st_mode==mode
    finally:release_tree(ctx)

@pytest.mark.parametrize('script,flags',[
 ('audio_survey.py','evidence/a --threshold 0.1 --json'),
 ('extract_hwpx.py','evidence/a --json --outdir work'),
 ('doc_diff.py','evidence/a evidence/b --markdown --all -o work.md'),
 ('dlp_log_table.py','evidence/a --time-col date --event-col event --src-col src --phase-col phase -o work.md'),
 ('merge_timeline.py','--manifest evidence/a --exif evidence/b --stt evidence/c --plaso evidence/d --anchor anchor -o work.json --report work-report.json'),
 ('video_integrity.py','evidence/a --json --no-decode'),
])
def test_r12_remaining_documented_direct_reads(ctx,script,flags):
    for launcher in ['python3',str(ROOT/'scripts/py')]:
        command=f'{launcher} {ROOT}/scripts/{script} {flags}'
        r=run('evidence_guard.mjs',event(ctx,{'command':command},'exec_command'),'pre-tool-use')
        assert r.returncode==0,(command,r.stderr)
        r=run('evidence_guard.mjs',event(ctx,{'command':command+' > evidence/result'},'exec_command'),'pre-tool-use')
        assert r.returncode==1

@pytest.mark.parametrize('option',['--outdir','--outdir='])
def test_r12_hwpx_output_still_denied(ctx,option):
    command=f'python3 {ROOT}/scripts/extract_hwpx.py evidence/a {option}{"" if option.endswith("=") else " "}evidence/out'
    assert run('evidence_guard.mjs',event(ctx,{'command':command},'exec_command'),'pre-tool-use').returncode==1
