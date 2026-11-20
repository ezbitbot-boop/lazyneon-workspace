// Read remote refs only: never fetch, update refs, or change installed code.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawnSync} from 'node:child_process';
export function checkUpdate({root, env=process.env, cacheDir=path.join(os.homedir(),'.cache','lazyneon-workspace'), now=Date.now(), run=spawnSync}={}) {
 if(env.LAZYNEON_OFFLINE==='1'||env.LAZYNEON_WS_NO_UPDATE_CHECK==='1') return '';
 const key=crypto.createHash('sha256').update(root).digest('hex');
 const stamp=path.join(cacheDir,key+'.check');
 const lock=stamp+'.lock';
 let locked=false;
 let pending=null;
 const ownerName='owner-'+crypto.randomUUID()+'.json';
 const started=Date.now();
 const git=(...args)=>{
  const remaining=4500-(Date.now()-started);
  if(remaining<=0)throw new Error('update notice budget exceeded');
  return run('git',['--no-optional-locks','-C',root,...args],{encoding:'utf8',timeout:Math.min(1500,remaining),env:{...env,GIT_TERMINAL_PROMPT:'0',GIT_SSH_COMMAND:'ssh -oBatchMode=yes -oConnectTimeout=1'},maxBuffer:65536});
 };
 try {
  fs.mkdirSync(cacheDir,{recursive:true});
  // Serialize stale-cache replacement as well as network checks.
  // Publish a complete lock atomically; a crash cannot leave an ownerless lock.
  pending=fs.mkdtempSync(lock+'.pending-');
  fs.writeFileSync(path.join(pending,ownerName),JSON.stringify({pid:process.pid,createdAt:now}));
  try {
   // POSIX rename can replace an empty directory: preserve unknown legacy locks.
   if(fs.existsSync(lock))throw new Error('Existing lock');
   fs.renameSync(pending,lock);
  } catch(error) {
   if(!fs.existsSync(lock))throw error;
   const entries=fs.readdirSync(lock);
   if(entries.length!==1||!/^owner(?:-[a-f0-9-]+)?\.json$/.test(entries[0]))return '';
   const ownerFile=path.join(lock,entries[0]);
   const owner=JSON.parse(fs.readFileSync(ownerFile,'utf8'));
   if(!Number.isSafeInteger(owner.pid)||owner.pid<=0||!Number.isFinite(owner.createdAt)||now-owner.createdAt<60000)return '';
   try {process.kill(owner.pid,0);return '';} catch(e) {if(e.code!=='ESRCH')return '';}
   // Unique owner names prevent a stale contender from deleting a new owner.
   // rmdir cannot remove a newly published, nonempty lock.
   fs.unlinkSync(ownerFile);
   fs.rmdirSync(lock);
   fs.renameSync(pending,lock);
  }
  pending=null;
  locked=true;
  try {if(now-Number(fs.readFileSync(stamp,'utf8'))<86400000)return '';}catch(e){if(e.code!=='ENOENT')throw e;}
  fs.writeFileSync(stamp,String(now));
  const local=git('rev-parse','HEAD');if(local.status!==0)return '';
  const remote=git('ls-remote','--exit-code','origin','refs/heads/main');
  const sha=remote.stdout?.trim().split(/\s/)[0];
  if(remote.status!==0||!(/^[a-f0-9]{40,64}$/).test(sha)||sha===local.stdout.trim())return '';
  const ahead=git('merge-base','--is-ancestor',local.stdout.trim(),sha);
  if(ahead.status===0)return 'LazyNeon Workspace: update available (upstream main is ahead; update manually).';
  // Unknown remote objects cannot be ordered using refs alone. Do not claim ahead.
  if(ahead.status!==1)return 'LazyNeon Workspace: update available (upstream main changed; ancestry unverified; review manually).';
 } catch {} // Best effort; offline/cache/timeout failures never interrupt session startup.
 finally {
  if(pending) {try {fs.rmSync(pending,{recursive:true,force:true});}catch{}}
  if(locked) {try {fs.unlinkSync(path.join(lock,ownerName));fs.rmdirSync(lock);}catch{}}
 }
 return '';
}
