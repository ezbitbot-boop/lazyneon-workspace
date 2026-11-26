"""Execute registered core + workspace hooks in both orders (r6 process style)."""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
def core_root():
    # Prefer the reviewed core checkout; fall back to installed named siblings.
    for sibling in [ROOT.parent/'lazyneon-core', *ROOT.parent.iterdir()]:
        try:
            if json.loads((sibling/'plugin.json').read_text()).get('name')=='lazyneon':
                return sibling
        except (OSError,ValueError):
            pass
    pytest.skip('Optional sibling LazyNeon core not installed')

@pytest.mark.parametrize('reverse',[False,True])
def test_registered_hook_coexistence(tmp_path, monkeypatch, reverse):
    monkeypatch.setenv('HOME',str(tmp_path))
    monkeypatch.setenv('USERPROFILE',str(tmp_path))
    monkeypatch.setenv('LAZYNEON_OFFLINE','1')
    monkeypatch.setenv('LAZYNEON_WS_PYTHON',sys.executable)
    monkeypatch.setenv('LAZYNEON_FEEDBACK_DIR',str(tmp_path/'.lazyneon/feedback'))
    plugins=[core_root(),ROOT]
    if reverse: plugins.reverse()
    payload={'workspacePaths':[str(tmp_path)],'cwd':str(tmp_path),'conversationId':'coexist',
             'toolCall':{'name':'read_file','args':{'path':'ordinary.txt'}},'task':'read a local file'}
    def run(event, data):
        outputs=[]
        for plugin in plugins:
            hooks=json.loads((plugin/'hooks.json').read_text())['hooks']
            for group in hooks.get(event,[]):
                if group.get('matcher') and not re.search(group['matcher'],data['toolCall']['name']):continue
                for hook in group.get('hooks',[group]):
                    command=shlex.split(hook['command']);assert command[0]=='node'
                    result=subprocess.run(command,cwd=plugin,input=json.dumps(data),text=True,capture_output=True,timeout=40)
                    assert result.returncode in (0,1),(hook,result.stderr)
                    obj=json.loads(result.stdout or '{}')
                    assert isinstance(obj,dict)
                    outputs.append((plugin,obj,result.returncode))
        return outputs
    for event in ['SessionStart','PreToolUse','PostToolUse','PreInvocation','Stop']:
        outputs=run(event,payload)
        assert all(obj.get('decision')!='deny' for _,obj,_ in outputs),outputs
        if event=='PostToolUse':assert all(obj=={} and code==0 for _,obj,code in outputs)
        if event=='SessionStart':assert all('injectSteps' in obj for _,obj,_ in outputs)
    write={**payload,'toolCall':{'name':'write_file','args':{'TargetFile':str(tmp_path/'evidence/disk.raw'),'content':'x'}}}
    outputs=run('PreToolUse',write)
    assert any(plugin==ROOT and obj.get('decision')=='deny' for plugin,obj,_ in outputs)
    # A guard's allow covers only its own check. Deny must dominate in the host.
    decisions=[obj.get('decision') for _,obj,_ in outputs]
    combined='deny' if 'deny' in decisions else 'allow'
    assert combined=='deny'
    assert ('deny' if 'deny' in list(reversed(decisions)) else 'allow')==combined
