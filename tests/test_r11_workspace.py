"""Round 11: real hook and throwaway OS protection regressions, offline only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from test_r6_workspace import ctx, run, event, batch, rows, ROOT

WRITES = [
 'perl -pi -e s/a/b/ {p}', "bash -c 'rm {p}'", "sh -c 'echo x > {p}'",
 'find {p} -delete', 'find {p} -exec rm {{}} \\;', 'xargs rm < {p}',
 'timeout 3 rm {p}', r'\rm {p}', 'shred -u {p}', 'ln -sf /etc/hosts {p}',
 'ln {p} alias', 'tar xf a.tar -C {p}', 'ditto x {p}', 'patch {p} x',
 'xattr -w name x {p}', 'git checkout HEAD -- {p}', 'git rm {p}',
 'git clean -fdx {p}', 'git restore {p}', 'git mv {p} x',
 'python3 -c "import shutil;shutil.copy(\'x\',\'{p}\')"',
 'python3 -c "import os;os.truncate(\'{p}\',0)"',
 'node -e "require(\'fs\').rmSync(\'{p}\')"',
 'node -e "require(\'fs\').copyFileSync(\'x\',\'{p}\')"',
 'lazyothers pii x --report {p}', 'lazyothers pii x --vault {p}',
 'Clear-Content {p}', 'Move-Item x {p}', 'Copy-Item x {p}', 'Rename-Item {p} x',
 '(Get-Item {p}).Delete()', 'sc {p} x', 'New-Item -Force {p}',
 'cmd /c ren {p} x', 'cmd /c copy /Y x {p}', 'xcopy x {p}', 'robocopy x {p}',
 'icacls {p} /grant Everyone:F', 'attrib -R {p}', 'wget -O {p} https://example.invalid',
 'echo x >| {p}', 'sed --in-place s/a/b/ {p}', 'echo `rm {p}`',
]
@pytest.mark.parametrize('template', WRITES)
def test_r11_allowlist_both_directions(ctx, template):
    for p, denied in [('evidence/a.txt',True), ('reports/a.txt',False)]:
        result=run('evidence_guard.mjs',event(ctx,{'command':template.format(p=p)},'exec_command'),'pre-tool-use')
        assert (result.returncode==1)==denied, result.stdout+result.stderr

@pytest.mark.parametrize('command', ['less evidence/a','xxd evidence/a','hexdump evidence/a','md5 evidence/a','sqlite3 -readonly evidence/a "select 1"','ffprobe evidence/a'])
def test_r11_read_allowlist(ctx,command):
    assert run('evidence_guard.mjs',event(ctx,{'command':command},'exec_command'),'pre-tool-use').returncode==0
    batch(event(ctx,{'command':command},'exec_command'));assert rows(ctx)==[]

def test_r11_morph_failure_priority(ctx):
    source=ctx/'a.txt';source.write_text('original');digest=hashlib.sha256(source.read_bytes()).hexdigest()
    (ctx/'manifest.json').write_text(json.dumps({'manifest_version':1,'root':str(ctx),'files':[{'path':'a.txt','sha256':digest}]}))
    stub=ctx/'noengine';stub.mkdir();(stub/'kiwipiepy.py').write_text('raise ImportError("unavailable")')
    report=ctx/'report.md'
    for value,status in [('a'*64,'FAIL'),(digest,'NOT_CHECKED')]:
        report.write_text('증거 a.txt SHA-256: '+value)
        r=run('hallucination_guard.mjs',event(ctx,{'path':str(report)}),env={'PYTHONPATH':str(stub)})
        assert json.loads(r.stdout)['status']==status,r.stderr

@pytest.mark.parametrize('command',["mkdir -p reports","sed -i '' 's/a/b/' note.txt",'git rm reports/old.md'])
def test_r11_quiet_targets(ctx,command):
    (ctx/'reports').mkdir();(ctx/'note.txt').write_text('ordinary text')
    batch(event(ctx,{'command':command},'exec_command'))
    assert not [r for r in rows(ctx) if r['kind']!='pass']

def test_r11_stale_and_live_lock(ctx):
    import time
    target=ctx/'a.txt';target.write_text('a');lock=ctx/'.lazyneon-workspace/audit_trail.jsonl.lock';lock.mkdir(parents=True)
    os.utime(lock,(time.time()-600,time.time()-600))
    r=run('evidence_guard.mjs',event(ctx,{'path':str(target)}),'post-tool-use')
    assert r.returncode==0 and 'recovered' in (ctx/'.lazyneon-workspace/audit_trail.jsonl').read_text()
    lock.mkdir();(lock/'owner.json').write_text(json.dumps({'pid':os.getpid(),'hostname':__import__('socket').gethostname(),'created':time.time()*1000}))
    r=run('evidence_guard.mjs',event(ctx,{'path':str(target)}),'post-tool-use')
    assert r.returncode==1 and lock.exists()

@pytest.mark.parametrize('number',['(02) 123-4567','(031) 1234-5678','(02)123-4567'])
def test_r11_bracket_phone(number):
    sys.path.insert(0,str(ROOT/'scripts'))
    from pii_patterns import _PHONE_RE
    assert _PHONE_RE.pattern.search(number)
    assert not _PHONE_RE.pattern.search('(202) 123-4567')

def cleanup(root):
    # Only caller-created throwaway trees; always remove immutable flags before deletion.
    if sys.platform=='darwin':subprocess.run(['chflags','-R','nouchg',str(root)],check=True)
    for p in [root,*root.rglob('*')]:
        if not p.is_symlink():
            if sys.platform.startswith('linux') and __import__('shutil').which('chattr'):subprocess.run(['chattr','-i',str(p)],capture_output=True)
            p.chmod(p.stat().st_mode|0o700)

def case(ctx,*args):
    return subprocess.run(['node',str(ROOT/'scripts/case_mode.mjs'),*map(str,args)],cwd=ctx,capture_output=True,text=True)

def test_r11_os_protection_and_unlock(ctx):
    evidence=ctx/'originals';evidence.mkdir();f=evidence/'a.txt';f.write_text('original')
    work=ctx/'work';digest=hashlib.sha256(f.read_bytes()).hexdigest()
    try:
        r=case(ctx,'init',evidence,'--out',work);assert r.returncode==0,r.stderr
        manifest=json.loads((work/'custody/hashes-start.json').read_text());assert manifest.get('protection')
        commands=[f"perl -pi -e s/original/changed/ '{f}'",f"bash -c 'rm \"{f}\"'",f"find '{f}' -delete",f"ln -sf /etc/hosts '{f}'",f"node -e \"require('fs').copyFileSync('/etc/hosts','{f}')\"",f"{sys.executable} -c \"open('{f}','w').write('changed')\"",f"cp /etc/hosts '{f}'",f"mv '{f}' '{ctx}/moved'",f"rm '{f}'",f"echo changed | tee '{f}'",f"dd if=/etc/hosts of='{f}'",f"echo changed > '{f}'"]
        import tarfile,io
        archive=ctx/'a.tar'
        with tarfile.open(archive,'w') as t:
            info=tarfile.TarInfo('a.txt');info.size=7;t.addfile(info,io.BytesIO(b'changed'))
        commands.append(f"tar xf '{archive}' -C '{evidence}'")
        for command in commands:
            r=subprocess.run(command,shell=True,capture_output=True,text=True)
            assert r.returncode!=0 or (command.startswith(('perl -pi','find ')) and 'Operation not permitted' in r.stderr),command
            assert hashlib.sha256(f.read_bytes()).hexdigest()==digest
        assert case(ctx,'verify','--case',work).returncode==0
        assert case(ctx,'unlock','--case',work).returncode!=0
        assert case(ctx,'unlock','--case',work,'--reason','throwaway regression').returncode==0
        f.write_text('changed');assert case(ctx,'close','--case',work).returncode==1
        assert 'throwaway regression' in (work/'custody/log.jsonl').read_text()
    finally:cleanup(ctx)

def test_r11_close_symlink_continues(ctx):
    evidence=ctx/'input';evidence.mkdir()
    for n in ['a','b','c']:(evidence/n).write_text('original')
    work=ctx/'work'
    try:
        assert case(ctx,'init',evidence,'--out',work).returncode==0
        cleanup(evidence)
        (evidence/'a').unlink();(evidence/'a').symlink_to(ctx/'outside');(evidence/'b').write_text('changed');(evidence/'c').unlink()
        r=case(ctx,'close','--case',work)
        assert 'CHANGED' in r.stderr and 'MISSING' in r.stderr,r.stderr
        log=json.loads((work/'custody/log.jsonl').read_text().splitlines()[-1]);assert log['type']=='close' and len(log['changed'])==2 and len(log['missing'])==1
    finally:cleanup(ctx)

@pytest.mark.parametrize('generator',['case_survey','court_evidence_sheet','generate_evidence_doc'])
def test_r11_generated_artifact_and_tamper(ctx,generator):
    sys.path.insert(0,str(ROOT/'scripts'))
    if generator=='case_survey':
        import case_survey
        text=case_survey.to_markdown({'root':'originals','generated_at':'2026-11-20 08:42','steps':{}})
    elif generator=='court_evidence_sheet':
        import court_evidence_sheet
        text=court_evidence_sheet.to_markdown([],'갑')
    else:
        import generate_evidence_doc
        generate_evidence_doc.generate_evidence_markdown({},[],ctx/'generated.md')
        text=(ctx/'generated.md').read_text()
    report=ctx/'report.md';report.write_text(text)
    r=run('hallucination_guard.mjs',event(ctx,{'path':str(report)}))
    assert r.returncode==0 and json.loads(r.stdout)['status']=='NOT_APPLICABLE',r.stderr
    report.write_text(text+'\n분석 결과 증거 987654개가 확인되었다.')
    r=run('hallucination_guard.mjs',event(ctx,{'path':str(report)}))
    assert r.returncode==1 and json.loads(r.stdout)['status']=='FAIL'

def test_r11_stt_default_and_output_refusal(ctx,monkeypatch):
    sys.path.insert(0,str(ROOT/'scripts'));import local_stt
    evidence=ctx/'originals';evidence.mkdir();audio=evidence/'a.wav';audio.write_bytes(b'fixture')
    work=ctx/'work';work.mkdir();monkeypatch.chdir(work)
    (work/'manifest.json').write_text(json.dumps({'manifest_version':1,'root':str(evidence),'files':[]}))
    monkeypatch.setattr(local_stt,'detect_engine',lambda **kw:'faster-whisper')
    monkeypatch.setattr(local_stt,'transcribe_file',lambda *a,**kw:{'engine':'test-local','segments':[]})
    assert local_stt.main([str(audio),'--allow-local-whisper'])==0
    assert list(evidence.iterdir())==[audio]
    assert (work/'transcripts/a.wav.transcript.json').is_file()
    assert local_stt.main([str(audio),'--out-dir',str(evidence/'transcripts')])==2
    assert not (evidence/'transcripts').exists()
    for out in [str(evidence/'sub'),str(work/'transcripts')]:
        r=run('evidence_guard.mjs',event(work,{'command':f'lazyforensic stt "{audio}" --out-dir "{out}" --allow-local-whisper'},'exec_command'),'pre-tool-use')
        assert r.returncode==(1 if str(evidence) in out else 0),r.stderr

def test_r11_ocr_scan_export_output_refusal(ctx,monkeypatch):
    sys.path.insert(0,str(ROOT/'scripts'));import local_ocr,case_survey,evidence_export
    evidence=ctx/'originals';evidence.mkdir();source=evidence/'a.png';source.write_bytes(b'fixture')
    work=ctx/'work';work.mkdir();monkeypatch.chdir(work)
    manifest=work/'manifest.json';manifest.write_text(json.dumps({'manifest_version':1,'root':str(evidence),'files':[]}))
    assert local_ocr.main([str(source),'--out',str(evidence/'ocr.json')])==2
    assert case_survey.main([str(evidence),'--markdown',str(evidence/'survey.md')])==2
    assert evidence_export.main([str(manifest),'-o',str(evidence/'export.json')])==2
    monkeypatch.setattr(local_ocr,'detect_engine',lambda *a:'tesseract')
    monkeypatch.setattr(local_ocr,'ocr_file',lambda *a,**kw:{'engine':'test','page_count':1,'blocks':[],'text':''})
    assert local_ocr.main([str(source)])==0 and (work/'ocr.json').is_file()
    assert evidence_export.main([str(manifest),'-o',str(work/'export.json')])==0

def test_r11_manifest_protection(ctx,monkeypatch):
    sys.path.insert(0,str(ROOT/'scripts'));import evidence_manifest
    evidence=ctx/'input';evidence.mkdir();(evidence/'a').write_text('a');monkeypatch.chdir(ctx)
    out=ctx/'manifest.json'
    try:
        assert evidence_manifest.main([str(evidence),'--protect','-o',str(out)])==0
        doc=json.loads(out.read_text());assert doc.get('protection')
        assert evidence_manifest.main([str(evidence),'--verify',str(out)])==0
        cleanup(evidence)
        assert evidence_manifest.main([str(evidence),'--verify',str(out)])==1
    finally:cleanup(ctx)

@pytest.mark.parametrize('variant',['NFC','NFD','uppercase','symlink'])
def test_r11_command_aliases_and_parent_workspace(ctx,variant):
    import unicodedata
    evidence=ctx/'증거Original';evidence.mkdir();(evidence/'a.txt').write_text('a')
    work=ctx/'work';(work/'custody').mkdir(parents=True)
    (work/'custody/hashes-start.json').write_text(json.dumps({'tool':'case_mode.mjs init','evidencePath':str(evidence),'files':[{'path':str(evidence/'a.txt')}]}))
    alias=str(evidence)
    if variant=='NFD':alias=unicodedata.normalize('NFD',alias)
    if variant=='uppercase':alias=alias.upper()
    if variant=='symlink':
        (ctx/'alias').symlink_to(evidence,target_is_directory=True);alias=str(ctx/'alias')
    for template in WRITES:
        r=run('evidence_guard.mjs',event(ctx,{'command':template.format(p=alias+'/a.txt')},'exec_command'),'pre-tool-use')
        assert r.returncode==1,(template,r.stdout,r.stderr)
    assert run('evidence_guard.mjs',event(ctx,{'command':f'cat "{alias}/a.txt"'},'exec_command'),'pre-tool-use').returncode==0
    assert run('evidence_guard.mjs',event(ctx,{'source':alias+'/a.txt','destination':str(ctx/'out')},'mcp__filesystem__move_file'),'pre-tool-use').returncode==1

@pytest.mark.parametrize('entry',['pii_mask','mask_korean_pii'])
def test_r11_pii_entrypoints(entry):
    sys.path.insert(0,str(ROOT/'scripts'));module=__import__(entry)
    for number in ['(02) 123-4567','(031)1234-5678']:
        result=module.mask_text(number) if entry=='pii_mask' else module.mask_text(number,module.ALL_TYPES)[0]
        assert result!=number and '5678' not in result and '4567' not in result
    ordinary='문서 번호 (202) 123-4567'
    assert module.mask_text(ordinary)==ordinary if entry=='pii_mask' else module.mask_text(ordinary,{'phone'})[0]==ordinary

def test_r11_manifest_unlock_reason(ctx,monkeypatch):
    sys.path.insert(0,str(ROOT/'scripts'));import evidence_manifest
    monkeypatch.chdir(ctx);evidence=ctx/'input';evidence.mkdir();(evidence/'a').write_text('a');out=ctx/'manifest.json'
    try:
        assert evidence_manifest.main([str(evidence),'--protect','-o',str(out)])==0
        assert case(ctx,'unlock','--manifest',out).returncode!=0
        assert case(ctx,'unlock','--manifest',out,'--reason','test cleanup').returncode==0
        assert 'test cleanup' in Path(str(out)+'.custody.jsonl').read_text()
        (evidence/'a').write_text('new')
    finally:cleanup(ctx)

def test_r11_hardlinks_rejected(ctx):
    evidence=ctx/'input';evidence.mkdir();source=evidence/'a';source.write_text('a');os.link(source,ctx/'alias')
    result=case(ctx,'init',evidence,'--out',ctx/'work')
    assert result.returncode!=0 and 'Hard-linked evidence' in result.stderr
    assert not source.stat().st_flags & 2 if sys.platform=='darwin' else source.stat().st_mode & 0o200

@pytest.mark.parametrize('command',['exiftool -@ script evidence/a','rg --pre=wipe pattern evidence/a','xxd x evidence/a','sqlite3 -readonly evidence/a ".shell rm evidence/a"','less --log-file=evidence/a evidence/b'])
def test_r11_read_program_write_flags_denied(ctx,command):
    assert run('evidence_guard.mjs',event(ctx,{'command':command},'exec_command'),'pre-tool-use').returncode==1

def test_r11_whisper_binary_scratch(ctx,monkeypatch):
    sys.path.insert(0,str(ROOT/'scripts'));import local_stt
    work=ctx/'work';work.mkdir();monkeypatch.chdir(work)
    evidence=ctx/'input';evidence.mkdir();audio=evidence/'a.wav';audio.write_bytes(b'a')
    executable=ctx/'whisper-test'
    executable.write_text('#!'+sys.executable+'\nimport sys,json\nfrom pathlib import Path\np=Path(sys.argv[sys.argv.index("-of")+1]+".json")\np.write_text(json.dumps({"transcription":[]}))\n')
    executable.chmod(0o700)
    assert local_stt.transcribe_binary(str(executable),audio,'ko')['segments']==[]
    assert list(evidence.iterdir())==[audio] and list(work.iterdir())==[]

def test_r11_real_scan_and_sheet(ctx,monkeypatch):
    sys.path.insert(0,str(ROOT/'scripts'));import case_survey,court_evidence_sheet
    evidence=ctx/'input';evidence.mkdir();(evidence/'a.txt').write_text('ordinary')
    work=ctx/'work';work.mkdir();monkeypatch.chdir(work)
    # Execute actual local stages; empty media sets do not invoke engines/network.
    case_survey.main([str(evidence),'-o',str(work/'survey.json'),'--markdown',str(work/'survey.md')])
    assert (work/'survey.md').is_file()
    assert court_evidence_sheet.main([str(work/'survey.json'),'-o',str(work/'sheet.md')])==0
    for p in [work/'survey.md',work/'sheet.md']:
        result=run('hallucination_guard.mjs',event(work,{'path':str(p)}))
        assert result.returncode==0 and json.loads(result.stdout)['status']=='NOT_APPLICABLE'
        batch(event(work,{'path':str(p)}))
    assert not [r for r in rows(ctx) if r['kind']!='pass']
    assert list(evidence.iterdir())==[evidence/'a.txt']

def test_r11_manifest_after_init(ctx,monkeypatch):
    sys.path.insert(0,str(ROOT/'scripts'));import evidence_manifest
    evidence=ctx/'input';evidence.mkdir();(evidence/'a').write_text('a');work=ctx/'work'
    try:
        assert case(ctx,'init',evidence,'--out',work).returncode==0
        monkeypatch.chdir(work)
        assert evidence_manifest.main([str(evidence),'-o',str(work/'manifest.json')])==0
        assert case(ctx,'close','--case',work).returncode==0
    finally:cleanup(ctx)

def test_r11_dead_pid_lock(ctx):
    import socket,time
    # Capture a real terminated child PID, not a guessed process identifier.
    child=subprocess.Popen([sys.executable,'-c','pass']);child.wait()
    target=ctx/'a.txt';target.write_text('a');lock=ctx/'.lazyneon-workspace/audit_trail.jsonl.lock';lock.mkdir(parents=True)
    (lock/'owner.json').write_text(json.dumps({'pid':child.pid,'hostname':socket.gethostname(),'created':time.time()*1000}))
    r=run('evidence_guard.mjs',event(ctx,{'path':str(target)}),'post-tool-use')
    assert r.returncode==0,r.stderr+r.stdout
    assert 'recovered' in (ctx/'.lazyneon-workspace/audit_trail.jsonl').read_text()

@pytest.mark.parametrize('template',WRITES)
def test_r11_real_hook_allowlist(ctx,template):
    from test_r6_oracle_workspace import dispatch
    for p,code in [('evidence/a.txt',1),('reports/a.txt',0)]:
        results=dispatch('PreToolUse',event(ctx,{'command':template.format(p=p)},'exec_command'))
        assert results[0].returncode==code,results[0].stdout+results[0].stderr

def test_r11_output_from_parent_workspace(ctx,monkeypatch):
    sys.path.insert(0,str(ROOT/'scripts'));from evidence_output import working_folder,safe_output
    evidence=ctx/'originals';evidence.mkdir();source=evidence/'a.wav';source.write_bytes(b'a');work=ctx/'work'
    try:
        assert case(ctx,'init',evidence,'--out',work).returncode==0
        monkeypatch.chdir(ctx)
        assert working_folder([source])==work
        assert safe_output(work/'out.json')==work/'out.json'
        with pytest.raises(ValueError):safe_output(evidence/'out.json')
    finally:cleanup(ctx)
