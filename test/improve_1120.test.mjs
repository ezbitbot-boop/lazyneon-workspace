import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawnSync} from 'node:child_process';
const root=path.resolve(import.meta.dirname,'..');
function temporary(fn){const p=fs.mkdtempSync(path.join(os.tmpdir(),'ws-improve-'));try{return fn(p);}finally{fs.rmSync(p,{recursive:true,force:true});}}
test('companion named sibling, minimum version, malformed and missing are advisory',async()=>{
 const {companionStatus,companionLine}=await import('../scripts/companion.mjs');
 temporary(p=>{
  const ws=path.join(p,'workspace');fs.mkdirSync(ws);
  assert.equal(companionStatus(ws).installed,false);
  assert.match(companionLine(companionStatus(ws)),/routing and general guards are not active; install LazyNeon core/);
  const sibling=path.join(p,'arbitrary-folder');fs.mkdirSync(sibling);
  for(const [version,compatible] of [['0.2.9',false],['0.3.0',true],['0.4.0',true],['1.0.0',true],['broken',false],['0.3.0-rc.1',false]]){
   fs.writeFileSync(path.join(sibling,'plugin.json'),JSON.stringify({name:'lazyneon',version}));
   assert.deepEqual(companionStatus(ws),{name:'lazyneon',installed:true,version,compatible});
  }
 });
});
test('missing core warning occurs every session; doctor WARN exits zero',()=>temporary(p=>{
 fs.mkdirSync(path.join(p,'scripts'));fs.mkdirSync(path.join(p,'rules'));
 for(const name of ['session_start.mjs','companion.mjs','doctor.mjs','update_notice.mjs','hook_workspace.mjs'])fs.copyFileSync(path.join(root,'scripts',name),path.join(p,'scripts',name));
 fs.copyFileSync(path.join(root,'rules/GEMINI.md'),path.join(p,'rules/GEMINI.md'));
 fs.copyFileSync(path.join(root,'plugin.json'),path.join(p,'plugin.json'));
 for(const name of ['session_start.mjs','session_start.mjs','doctor.mjs']){
  const r=spawnSync(process.execPath,[path.join(p,'scripts',name)],{input:'{}',encoding:'utf8',env:{...process.env,LAZYNEON_OFFLINE:'1'}});
  assert.equal(r.status,0,r.stderr);assert.match(r.stdout,/WARN.*routing and general guards are not active; install LazyNeon core/);
 }
}));
test('stale dead-owner update lock recovers, live and fresh owners remain',async()=>{
 const {checkUpdate}=await import('../scripts/update_notice.mjs');
 for(const state of ['dead','live','fresh'])temporary(p=>{
  const now=Date.now();const key=crypto.createHash('sha256').update(p).digest('hex');const lock=path.join(p,key+'.check.lock');fs.mkdirSync(lock);
  fs.writeFileSync(path.join(lock,'owner.json'),JSON.stringify({pid:state==='live'?process.pid:2147483647,createdAt:state==='fresh'?now:now-120000}));
  let calls=0;checkUpdate({root:p,cacheDir:p,env:{},now,run:()=>{calls++;return {status:1};}});
  assert.equal(calls>0,state==='dead');assert.equal(fs.existsSync(lock),state!=='dead');
 });
});
test('multiple named siblings prefer newest stable core over an old installation',async()=>{
 const {companionStatus}=await import('../scripts/companion.mjs');
 temporary(p=>{
  const ws=path.join(p,'workspace');fs.mkdirSync(ws);
  for(const [folder,version] of [['a-old','0.2.0'],['z-current','0.4.0']]){
   fs.mkdirSync(path.join(p,folder));fs.writeFileSync(path.join(p,folder,'plugin.json'),JSON.stringify({name:'lazyneon',version}));
  }
  assert.equal(companionStatus(ws).version,'0.4.0');
 });
});
test('ownerless legacy lock is preserved without guessing process liveness',async()=>{
 const {checkUpdate}=await import('../scripts/update_notice.mjs');
 temporary(p=>{
  const key=crypto.createHash('sha256').update(p).digest('hex');const lock=path.join(p,key+'.check.lock');fs.mkdirSync(lock);
  let calls=0;checkUpdate({root:p,cacheDir:p,env:{},run:()=>{calls++;return {status:1};}});
  assert.equal(calls,0);assert.ok(fs.existsSync(lock));
 });
});
