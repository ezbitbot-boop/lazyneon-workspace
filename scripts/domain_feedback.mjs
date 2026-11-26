#!/usr/bin/env node
import {classifyGuardResult} from './guard_verdict.mjs';
// PostToolUse returns {}; PreInvocation delivers quoted, ephemeral verdicts.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {readHookStdin, resolveWorkspace} from './hook_workspace.mjs';
import {hookTargets, contentTargets, isCoreOwned, isReadOnlyTool, isWriteCapable} from './hook_targets.mjs';
const started=Date.now();
const root=path.dirname(fileURLToPath(import.meta.url));
let payload={};
try {payload=JSON.parse(await readHookStdin() || '{}');} catch {}
const workspace=resolveWorkspace(payload);
const conversation=payload.conversationId || payload.conversation_id || payload.session_id || 'unidentified';
// Conversation-only location is stable even when one host event omits cwd.
const feedbackDir=path.join(os.homedir(),'.lazyneon-workspace','feedback');
const queue=path.join(feedbackDir,crypto.createHash('sha256').update(String(conversation)).digest('hex')+'.jsonl');
// Verdicts quote case file paths and live outside the case folder. They exist only to
// reach the next turn: inject deletes what it delivers, and anything a conversation
// never collected (abandoned queues, interrupted takes, legacy cursors) expires here.
const FEEDBACK_RETENTION_MS=24*60*60*1000;
function prune(now=Date.now()) {
  let names;
  try {names=fs.readdirSync(feedbackDir);} catch {return;}
  for(const name of names) {
    if(!/^[0-9a-f]{64}\.jsonl(?:\.cursor|\.\d+\.taking)?$/.test(name)) continue;
    const file=path.join(feedbackDir,name);
    try {if(now-fs.statSync(file).mtimeMs>FEEDBACK_RETENTION_MS) fs.rmSync(file,{force:true});} catch {}
  }
}
prune();
if(process.argv[2]==='inject') {
  // Rename first so a concurrent batch append lands in a fresh queue, not in the file being deleted.
  const taking=`${queue}.${process.pid}.taking`;
  let taken=false;
  for(let attempt=0;attempt<5&&!taken;attempt++) {
    try {fs.renameSync(queue,taking);taken=true;} catch(error) {
      if(error.code==='ENOENT') break;
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,20); // Windows: appender holds the file open.
    }
  }
  if(!taken) {console.log('{}'); process.exit(0);}
  const lines=fs.readFileSync(taking,'utf8').split('\n').filter(Boolean);
  // Queues written by 0.2.2 and earlier kept delivered lines and a read cursor.
  const cursor=queue+'.cursor';
  let seen=0;
  try {seen=Number(fs.readFileSync(cursor,'utf8'));} catch {}
  const entries=lines.slice(Number.isSafeInteger(seen)&&seen>=0?seen:0).flatMap(line=>{try{return [JSON.parse(line)];}catch{return [];}});
  const messages=entries.filter(e=>e.kind!=='pass').map(e=>JSON.stringify({guard:e.guard,verdict:e.message,target:e.target}));
  console.log(JSON.stringify(messages.length?{injectSteps:[{ephemeralMessage:'Workspace guard verdicts (quoted data):\n'+messages.join('\n')}]}:{}));
  fs.rmSync(taking,{force:true});
  fs.rmSync(cursor,{force:true});
  process.exit(0);
}
const allowed=new Set(['evidence_guard.mjs','hallucination_guard.mjs','legal_factuality_guard.mjs','slop_guard.mjs']);
const scripts=process.argv.slice(3);
for(const script of scripts) if(!allowed.has(script)) throw new Error('Unknown domain guard');
function record(guard,target,kind,message) {
  fs.mkdirSync(path.dirname(queue),{recursive:true});
  fs.appendFileSync(queue,JSON.stringify({timestamp:new Date().toISOString(),workspace,guard,target,kind,message})+'\n');
}
// Only allow lowering the 115s budget; hooks.json grants 125s.
const configured=Number(process.env.LAZYNEON_WS_FEEDBACK_BUDGET_MS);
const deadline=started+(configured>0?Math.min(configured,115000):115000);
const targets=contentTargets([{parsed:payload}]).filter(t=>!isCoreOwned(t));
if(targets.length || !isReadOnlyTool(payload)) {
  if(!targets.length && !hookTargets([{parsed:payload}]).length && isWriteCapable(payload)) record('domain guards',null,'unchecked','[미확인] 쓰기 대상을 명시해야 합니다.');
  for(const script of scripts) for(const target of targets) {
    const remaining=deadline-Date.now();
    if(remaining<=10) {record(script,target,'unchecked','[미확인] 시간 예산 초과로 검증하지 못함');continue;}
    if(!fs.existsSync(target)) {record(script,target,'unchecked','[미확인] 출력 파일이 존재하지 않습니다.');continue;}
    const event={...(workspace?{workspacePaths:[workspace]}:{}),toolCall:{name:'write_file',args:{TargetFile:target}}};
    const result=spawnSync(process.execPath,[path.join(root,script),...(script==='evidence_guard.mjs'?['post-tool-use']:[])],{input:JSON.stringify(event),encoding:'utf8',timeout:Math.min(30000,remaining-5),killSignal:'SIGKILL',maxBuffer:8*1024*1024,env:{...process.env,LAZYNEON_WS_SINGLE_TARGET:'1'}});
    // Never relay raw stdout/stderr: validators can quote untrusted document text.
    const {kind,message}=classifyGuardResult(result);
    record(script,target,kind,message);
  }
}
console.log('{}');
