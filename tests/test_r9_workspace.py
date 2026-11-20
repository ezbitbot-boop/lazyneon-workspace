"""Round 9 regressions: real hook processes, local fixtures only."""
import json
import subprocess
import sys
from pathlib import Path
import pytest
from test_r6_workspace import ctx, run, event, batch, rows, ROOT

def js(code):
    p=subprocess.run(['node','--input-type=module','-e',code],cwd=ROOT,text=True,capture_output=True)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)

@pytest.mark.parametrize('rel,owned', [('.lazyneon/ulw-research/t1/SYNTHESIS.md',False),('.lazyneon/ulw-research/t1/report.md',False),('.lazyneon/ulw-research/t1/verify-x.md',True),('.lazyneon/ulw-research/t1/sources/a.txt',False),('.lazyneon/ulw-research/brief.md',False),('.lazyneon/report.md',False)])
def test_r9_core_paths(ctx,rel,owned):
    p=ctx/rel;p.parent.mkdir(parents=True);p.write_text('민법 제1500조.')
    batch(event(ctx,{'path':str(p)}))
    assert (rows(ctx)==[]) == owned
    assert (not (ctx/'.lazyneon-workspace/audit_trail.jsonl').exists()) == owned

@pytest.mark.parametrize('command',['exiftool -TagsFromFile x.jpg evidence/a.jpg','exiftool "-Comment<FileName" evidence/a.jpg','rg --pre=/tmp/w.sh x evidence/','node ./classify-task.mjs evidence/a.jpg','node /tmp/report-tools.mjs claims snapshot evidence/a.jpg'])
def test_r9_lock(ctx,command):
    r=run('evidence_guard.mjs',event(ctx,{'command':command},'run_command'),'pre-tool-use')
    assert r.returncode==1 and 'deny' in r.stdout

@pytest.mark.parametrize('name',['search_replace','SearchReplace','str_replace','StrReplace','multi_edit','MultiReplaceFileContent','search_update'])
def test_r9_edit_variants(ctx,name):
    p=ctx/'brief.md';p.write_text('민법 제1500조에 따라 청구한다.')
    batch(event(ctx,{'file_path':str(p)},name),'legal_factuality_guard.mjs')
    assert any(r['kind']=='fail' for r in rows(ctx))

@pytest.mark.parametrize('cmd',['cp src.md reports/소장.md','cat x | tee reports/소장.md','mv src.md reports/소장.md','dd if=x of=reports/소장.md','install src.md reports/소장.md','rsync src.md reports/소장.md','python gen.py -o reports/소장.md'])
def test_r9_shell_targets(ctx,cmd):
    p=ctx/'reports/소장.md';p.parent.mkdir();p.write_text('민법 제1500조.')
    batch(event(ctx,{'command':cmd},'run_command'),'legal_factuality_guard.mjs')
    assert any(r['kind']=='fail' and r['target']==str(p) for r in rows(ctx))

@pytest.mark.parametrize('rel',['brief.md','scope.md','sub/.lazyneon-workspace/소장.md'])
def test_r9_no_basename_exemption(ctx,rel):
    p=ctx/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('민법 제1500조.')
    r=run('legal_factuality_guard.mjs',event(ctx,{'path':str(p)}))
    assert r.returncode==1

def test_r9_renamed_audit(ctx):
    sys.path.insert(0,str(ROOT/'scripts'))
    from report_core import verified_evidence_text
    p=ctx/'renamed.jsonl';p.write_text(json.dumps({'timestamp':'now','file':'a','sha256':'a'*64}))
    with pytest.raises(ValueError): verified_evidence_text(p)

def test_r9_pii_stdout(ctx):
    p=ctx/'pii.txt';p.write_text('010-1234-5678 4111-1111-1111-1111')
    r=subprocess.run([sys.executable,str(ROOT/'scripts/pii_mask.py'),str(p)],capture_output=True,text=True)
    assert '010-1234-5678' not in r.stdout and '4111-1111-1111-1111' not in r.stdout

def test_r9_moonshine_korean(monkeypatch):
    sys.path.insert(0,str(ROOT/'scripts'));import local_stt
    monkeypatch.setattr(local_stt.importlib.util,'find_spec',lambda n: n=='moonshine')
    monkeypatch.setattr(local_stt.shutil,'which',lambda n: None)
    assert local_stt.detect_engine() is None

@pytest.mark.parametrize('file,needle',[('.gitignore','*.pii-vault.json'),('skills/court-evidence-stamper/SKILL.md','--allow-sample'),('skills/lazyforensic/SKILL.md','pii_mask.py <대상> --mask'),('docs/EXIT_CODES.md','--enforce'),('skills/legal-draft-builder/SKILL.md','되돌리'),('requirements.txt','# Required: Korean morphological grounding'),('scripts/py.cmd','py.ps1')])
def test_r9_document_contract(file,needle):
    assert needle in (ROOT/file).read_text()

def test_r9_structured_relay():
    result=js("import {classifyGuardResult as c} from './scripts/guard_verdict.mjs'; console.log(JSON.stringify([c({status:0,stdout:'{}',stderr:'미확인/report.md HINT 미확인으로 둘 것'}),c({status:1,stdout:JSON.stringify({code:'MORPH_UNAVAILABLE'})}),c({status:null,signal:'SIGKILL'}),c({status:0,stdout:JSON.stringify({status:'FAIL'})})]));")
    assert result[0]['kind']=='unchecked'  # r10: missing verdict is not PASS
    assert '형태소 엔진 없음' in result[1]['message']
    assert 'timeout' in result[2]['message']
    assert result[3]['kind']=='fail'

def test_r9_symlink_root(ctx):
    real=ctx/'real';real.mkdir();(real/'a.txt').write_text('original')
    link=ctx/'ev';link.symlink_to(real,target_is_directory=True)
    p=subprocess.run(['node',str(ROOT/'scripts/case_mode.mjs'),'init',str(link),'--out',str(ctx/'case')],capture_output=True,text=True)
    assert p.returncode != 0 and 'Symlink evidence roots' in p.stderr

@pytest.mark.parametrize('script,args',[('slop_guard.mjs',['--file','x.md']),('case_mode.mjs',['--help'])])
def test_r9_symlink_cli(ctx,script,args):
    link=ctx/'plugin';link.symlink_to(ROOT,target_is_directory=True)
    (ctx/'x.md').write_text('ordinary notes')
    p=subprocess.run(['node',str(link/'scripts'/script),*args],cwd=ctx,capture_output=True,text=True)
    assert p.returncode == 0, p.stderr
    if script == 'slop_guard.mjs':
        result=json.loads(p.stdout)
        assert result['file']=='x.md' and 'weight' in result
    else: assert 'Usage:' in p.stdout+p.stderr

def test_r9_osint_consent(ctx):
    sys.path.insert(0,str(ROOT/'scripts'));import osint_username
    with pytest.raises(SystemExit) as e: osint_username.main(['testuser'])
    assert e.value.code==2

@pytest.mark.parametrize('file,needle',[('bin/lazyothers','sheet --input-json'),('bin/lazyothers.ps1','morph --source'),('skills/media-analysis/SKILL.md','URL을 주면 YouTube에 접속'),('skills/media-analysis/SKILL.md','--upload-audio --lang ko'),('scripts/setup_forensic_env.py','if g != "osint"'),('scripts/local_only_audit.py','external_username_query')])
def test_r9_more_docs(file,needle):
    assert needle in (ROOT/file).read_text()

def test_r9_init_hint():
    s=(ROOT/'scripts/case_mode.mjs').read_text()
    assert 'case-mode close --case' in s and 'を실행하면' not in s

def test_r9_zero_frames():
    import ast
    tree=ast.parse((ROOT/'skills/forensic-video/scripts/watch.py').read_text())
    # Explicit zero must not be replaced by default frame caps.
    assert not any(isinstance(n,ast.BoolOp) and isinstance(n.op,ast.Or) and any(isinstance(v,ast.Name) and v.id=='max_frames' for v in n.values) for n in ast.walk(tree))

@pytest.mark.parametrize('value',['+82 (0)10-1234-5678','(+82) 10-1234-5678','+82 2-123-4567'])
def test_r9_international_pii(value):
    sys.path.insert(0,str(ROOT/'scripts'));import pii_mask,mask_korean_pii
    assert pii_mask.detect_in_text(value)
    assert pii_mask.mask_text(value)!=value
    assert mask_korean_pii.mask_text(value,mask_korean_pii.ALL_TYPES)[0]!=value

@pytest.mark.parametrize('result_key',['tool_response','toolResult'])
def test_r9_output_not_target(ctx,result_key):
    p={'workspacePaths':[str(ctx)],'toolCall':{'name':'write_file','parameters':{'path':'brief.md'}},result_key:{'path':'SECRET.md'}}
    found=js("import {contentTargets} from './scripts/hook_targets.mjs'; console.log(JSON.stringify(contentTargets([{parsed:"+json.dumps(p)+"}])));")
    assert found==[str(ctx/'brief.md')]

def test_r9_json_brief(ctx):
    p=ctx/'outcome.json';p.write_text(json.dumps({'text':'민법 제1500조.'},ensure_ascii=False))
    assert run('legal_factuality_guard.mjs',event(ctx,{'path':str(p)})).returncode==1

def test_r9_morph_reason(ctx):
    import shlex
    wrapper=ctx/'python-no-site';wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' -S '+shlex.quote(str(ROOT/'tests/morph_without_engine.py'))+' "$@"\n');wrapper.chmod(0o755)
    source=ctx/'source.txt';source.write_text('evidence')
    run('evidence_guard.mjs',event(ctx,{'path':str(source)}),'post-tool-use')
    report=ctx/'감정보고서.md';report.write_text('# 감정 보고서\n검증 미완료')
    batch(event(ctx,{'path':str(report)}),'hallucination_guard.mjs',env={'LAZYNEON_WS_PYTHON':str(wrapper)})
    assert any('형태소 엔진 없음' in r['message'] for r in rows(ctx))
    assert not any(r['kind']=='pass' for r in rows(ctx))

def test_r9_maskers_no_reconstruction():
    sys.path.insert(0,str(ROOT/'scripts'));import pii_mask,mask_korean_pii
    value='010-1234-5678 4111-1111-1111-1111'
    a=pii_mask.mask_text(value);b=mask_korean_pii.mask_text(value,mask_korean_pii.ALL_TYPES)[0]
    assert '5678' not in a+b and '4111' not in a+b

def test_r9_dependency_absence_tests_unconditional():
    import ast
    tree=ast.parse((ROOT/'test/test_forensic_tools2.py').read_text())
    for node in ast.walk(tree):
        if isinstance(node,ast.FunctionDef) and node.name in ['test_fail_closed_without_sherlock','test_no_fpcalc_exit_3','test_no_ffmpeg_exit_3']:
            assert not any(isinstance(n,ast.Attribute) and n.attr=='skipTest' for n in ast.walk(node))

def test_r9_zero_frames_runtime(ctx,monkeypatch,capsys):
    import importlib.util
    spec=importlib.util.spec_from_file_location('r9_watch',ROOT/'skills/forensic-video/scripts/watch.py');watch=importlib.util.module_from_spec(spec);spec.loader.exec_module(watch)
    monkeypatch.setattr(sys,'argv',['watch.py','local.mp4','--max-frames','0','--out-dir',str(ctx/'frames'),'--json'])
    monkeypatch.setattr(watch,'resolve_local',lambda _: {'video_path':'local.mp4','info':{}})
    def forbidden(*a,**kw): pytest.fail('zero-frame request invoked frame extraction')
    for name in ['get_metadata','extract_keyframes','extract_scene_or_uniform','extract_at_timestamps']:
        monkeypatch.setattr(watch,name,forbidden)
    assert watch.main()==0
    assert json.loads(capsys.readouterr().out)['frames']==[]

@pytest.mark.parametrize('cmd',['exiftool -j evidence/a.jpg','rg x evidence/'])
def test_r9_read_controls(ctx,cmd):
    assert run('evidence_guard.mjs',event(ctx,{'command':cmd},'run_command'),'pre-tool-use').returncode==0

def test_r9_matcher_edit_names():
    hooks=json.loads((ROOT/'hooks.json').read_text())
    edits=['write_file','search_replace','str_replace','multi_edit','search_update','apply_patch','generate_document','fill_form','redact_document']
    for phase in ['PreToolUse','PostToolUse']:
        assert js('console.log(JSON.stringify('+json.dumps(edits+['exec_command'])+'.every(n=>'+json.dumps([h['matcher'] for h in hooks['hooks'][phase]])+'.some(r=>new RegExp(r).test(n)))));')
    assert js("import {isReadOnlyTool} from './scripts/hook_targets.mjs'; console.log(JSON.stringify("+json.dumps(edits)+".map(name=>isReadOnlyTool({toolCall:{name,args:{}}}))));")==[False]*len(edits)
