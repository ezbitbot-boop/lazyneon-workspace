import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

test('update notice: refs only, TTL, opt-outs, timeout and ancestry', async () => {
 const {checkUpdate} = await import('../scripts/update_notice.mjs');
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'update-notice-'));
 try {
  const calls=[];
  const run=(cmd,args,opts)=>{
   calls.push({cmd,args,opts});
   if(args.includes('ls-remote')) return {status:0,stdout:'b'.repeat(40)+'\trefs/heads/main\n'};
   if(args.includes('rev-parse')) return {status:0,stdout:'a'.repeat(40)};
   if(args.includes('merge-base')) return {status:args.at(-1)==='b'.repeat(40)?0:1,stdout:''};
   return {status:1,stdout:''};
  };
  const options={root:dir,cacheDir:dir,env:{},run,now:100000000};
  assert.match(checkUpdate(options), /update available/);
  assert.equal(checkUpdate(options),'');
  assert.match(checkUpdate({...options,now:options.now+86400001}), /update available/);
  assert.equal(calls.filter(c=>c.args.includes('ls-remote')).length,2);
  assert.equal(checkUpdate({...options,now:options.now+2*86400001,env:{LAZYNEON_OFFLINE:'1'}}),'');
  assert.equal(checkUpdate({...options,now:options.now+2*86400001,env:{LAZYNEON_WS_NO_UPDATE_CHECK:'1'}}),'');
  assert.ok(calls.every(c=>c.opts.timeout <= 2000));
  const later={...options,now:options.now+2*86400001};
  assert.equal(checkUpdate({...later,run:()=>({status:null,error:new Error('timeout')})}),'');
  assert.equal(checkUpdate({...later,run:()=>{throw Error('must remain cached');}}),'');
  assert.ok(calls.every(c=>!c.args.some(x=>['fetch','pull','checkout'].includes(x))));
 } finally {fs.rmSync(dir,{recursive:true,force:true});}
});

test('same, behind, diverged, unknown and unreachable upstream', async () => {
 const {checkUpdate}=await import('../scripts/update_notice.mjs');
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'notice-states-'));
 try {
  let now=100000000;
  for(const [remote,ancestor,expected] of [
   ['a'.repeat(40),0,''], ['b'.repeat(40),1,''],
   ['b'.repeat(40),128,'ancestry unverified'], ['',128,''],
  ]) {
   const run=(cmd,args)=>args.includes('rev-parse')?{status:0,stdout:'a'.repeat(40)}:
    args.includes('ls-remote')?{status:remote?0:1,stdout:remote+'\trefs/heads/main'}:{status:ancestor};
   const result=checkUpdate({root:dir,cacheDir:dir,env:{},now:now+=86400001,run});
   expected?assert.ok(result.includes(expected)):assert.equal(result,'');
  }
 } finally {fs.rmSync(dir,{recursive:true,force:true});}
});
