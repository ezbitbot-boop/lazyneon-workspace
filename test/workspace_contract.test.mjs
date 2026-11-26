import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
function session(cwd, payload={}) {
 const r=spawnSync(process.execPath,[path.join(root,'scripts/session_start.mjs')],{cwd,input:JSON.stringify({workspacePaths:[cwd],...payload}),encoding:'utf8'});
 assert.equal(r.status,0,r.stderr);
 return JSON.parse(r.stdout).injectSteps[0].systemMessage.systemMessage;
}
function temporary(fn) {const p=fs.mkdtempSync(path.join(os.tmpdir(),'neon-contract-'));try {fn(p);}finally{fs.rmSync(p,{recursive:true,force:true});}}
test('session without optional core files creates no state',()=>temporary(p=>{
 const msg=session(p);assert.match(msg,/LazyNeon Workspace 0.2.2/);assert.match(msg,/세션 모델: 미확인/);assert.deepEqual(fs.readdirSync(p),[]);
}));
test('core inputs are not reinjected or changed',()=>temporary(p=>{
 const core=path.join(p,'.lazyneon');fs.mkdirSync(core);
 for(const name of ['pins.md','ulw-scope.md'])fs.writeFileSync(path.join(core,name),`sentinel ${name}`);
 const before=fs.readdirSync(core).map(n=>[n,fs.readFileSync(path.join(core,n),'utf8')]);
 const msg=session(p,{modelName:'gemini-4-neon'});
 assert.doesNotMatch(msg,/sentinel pins.md/);assert.doesNotMatch(msg,/sentinel ulw-scope.md/);assert.match(msg,/세션 모델: gemini-4-neon/);
 assert.deepEqual(fs.readdirSync(core).map(n=>[n,fs.readFileSync(path.join(core,n),'utf8')]),before);
 assert.deepEqual(fs.readdirSync(p),['.lazyneon']);
}));
test('domain relay registers exactly four domain guards and no generic hooks',()=>{
 const hooks=JSON.parse(fs.readFileSync(path.join(root,'hooks.json'))).hooks;
 const guards=['evidence_guard.mjs','hallucination_guard.mjs','legal_factuality_guard.mjs','slop_guard.mjs'];
 assert.deepEqual(Object.keys(hooks).sort(),['PostToolUse','PreInvocation','PreToolUse','SessionStart']);
 assert.equal(hooks.PostToolUse.length,1);
 assert.deepEqual(hooks.PostToolUse[0].hooks.map(h=>h.command),[
  `node ./scripts/domain_feedback.mjs batch ${guards.join(' ')}`
 ]);
 assert.deepEqual(hooks.PreInvocation.map(h=>h.command),['node ./scripts/domain_feedback.mjs inject']);
 assert.deepEqual(hooks.PreToolUse.map(g=>g.hooks.map(h=>h.command)),[['node ./scripts/evidence_guard.mjs pre-tool-use']]);
 assert.deepEqual(hooks.SessionStart.map(h=>h.command),['node ./scripts/session_start.mjs']);
 assert.ok(!fs.existsSync(path.join(root,'scripts/post_tool_feedback.mjs')));
 for(const generic of ['markdown','json','write_chunk','stop_claim','lookup']) {
  assert.doesNotMatch(JSON.stringify(hooks),new RegExp(`${generic}(?:_structure)?_guard`));
 }
});
test('domain relay rejects generic guards without executing them',()=>temporary(p=>{
 for(const guard of ['markdown_structure_guard.mjs','json_guard.mjs','write_chunk_guard.mjs','stop_claim_guard.mjs','lookup_guard.mjs']) {
  const r=spawnSync(process.execPath,[path.join(root,'scripts/domain_feedback.mjs'),'batch',guard],{
   cwd:p,input:JSON.stringify({workspacePaths:[p],conversationId:'domain-only',tool_name:'write_file',tool_input:{}}),encoding:'utf8'
  });
  assert.notEqual(r.status,0);
  assert.match(r.stderr,/Unknown domain guard/);
  assert.deepEqual(fs.readdirSync(p),[]);
 }
}));
test('catalog is exactly owner approved; experiments are not discoverable',()=>{
 const statuses=JSON.parse(fs.readFileSync(path.join(root,'docs/review/skill-status.json')));
 const active=fs.readdirSync(path.join(root,'skills')).filter(n=>fs.existsSync(path.join(root,'skills',n,'SKILL.md'))).sort();
 assert.deepEqual(active,[...statuses.KEEP,...statuses['KEEP-AFTER-FIX']].sort());
 for(const n of statuses['DISABLED-EXPERIMENTAL'])assert.ok(fs.existsSync(path.join(root,'experimental',n,'SKILL.md')));
});
test('case hashes detect content changes with isolated policy state',()=>temporary(p=>{
 const source=path.join(p,'sample.bin');fs.writeFileSync(source,'original');const out=path.join(p,'case');
 const run=(args)=>spawnSync(process.execPath,[path.join(root,'scripts/case_mode.mjs'),...args],{cwd:p,encoding:'utf8'});
 const init=run(['init',source,'--out',out]);assert.equal(init.status,0,init.stderr);
 assert.ok(fs.existsSync(path.join(out,'.lazyneon-workspace','case-settings.json')));
 assert.equal(run(['close','--case',out]).status,0);
 const unlock=run(['unlock','--case',out,'--reason','simulate tampering']);assert.equal(unlock.status,0,unlock.stderr);
 fs.writeFileSync(source,'changed');const close=run(['close','--case',out]);assert.equal(close.status,1);assert.match(close.stderr,/INTEGRITY FAIL/);assert.match(close.stderr,/CHANGED/);
}));
