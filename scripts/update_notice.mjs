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
 const git=(...args)=>run('git',['--no-optional-locks','-C',root,...args],{encoding:'utf8',timeout:1500,env:{...env,GIT_TERMINAL_PROMPT:'0',GIT_SSH_COMMAND:'ssh -oBatchMode=yes -oConnectTimeout=1'},maxBuffer:65536});
 try {
  fs.mkdirSync(cacheDir,{recursive:true});
  // Serialize stale-cache replacement as well as network checks.
  fs.mkdirSync(lock);locked=true;
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
 finally {if(locked) {try {fs.rmdirSync(lock);}catch{}}}
 return '';
}
