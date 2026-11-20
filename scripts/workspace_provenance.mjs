import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
const root=fileURLToPath(new URL('../',import.meta.url));
export function workspaceProvenance() {
 const git=(...args)=>{const p=spawnSync('git',['--no-optional-locks','-C',root,...args],{encoding:'utf8',timeout:2000});return p.status===0?p.stdout.trim():null;};
 let version='unknown';try{version=JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8')).version;}catch{}
 const top=git('rev-parse','--show-toplevel');
 const valid=top && path.resolve(top)===path.resolve(root);
 const status=valid?git('status','--porcelain','--untracked-files=normal'):null;
 return {workspace_version:version,git_commit:(valid?git('rev-parse','HEAD'):null)||'unknown',git_dirty:status===null?'unknown':Boolean(status)};
}
