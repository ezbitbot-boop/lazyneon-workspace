import {spawn} from 'node:child_process';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {pythonCandidates} from './python_runtime.mjs';
const script=fileURLToPath(new URL('./evidence_protection.py',import.meta.url));
export async function protection(action, data) {
  // Select an interpreter before any mutation; never retry a failed lock operation.
  for (const candidate of pythonCandidates(path.dirname(path.dirname(script)))) {
    const probe=await execute(candidate,['-c','import sys; print(sys.version_info.major)'],'');
    if(probe.error || probe.code!==0 || probe.stdout.trim()!=='3') continue;
    const result=await execute(candidate,[script],JSON.stringify({action,...data}));
    if(result.error || result.code!==0) throw new Error(result.error?.message || result.stderr || 'OS protection failed');
    return JSON.parse(result.stdout);
  }
  throw new Error('Python 3 unavailable; configure LAZYNEON_WS_PYTHON');
}
function execute(candidate,args,input) {
  return new Promise(resolve=>{
    const child=spawn(candidate.cmd,[...candidate.pre,...args],{stdio:['pipe','pipe','pipe']});
    const out=[],err=[];
    child.stdout.on('data',chunk=>out.push(chunk));
    child.stderr.on('data',chunk=>err.push(chunk));
    child.on('error',error=>resolve({error}));
    child.on('close',code=>resolve({code,stdout:Buffer.concat(out).toString('utf8'),stderr:Buffer.concat(err).toString('utf8')}));
    child.stdin.on('error',()=>{});
    child.stdin.end(input);
  });
}
