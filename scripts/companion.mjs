// Read sibling manifests only; never import companion code or install anything.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
export function companionStatus(pluginRoot=root) {
 const missing={name:'lazyneon',installed:false,version:null,compatible:null};
 const found=[];
 try {
  const parent=path.dirname(fs.realpathSync(pluginRoot));
  for(const entry of fs.readdirSync(parent,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))) {
   if(!entry.isDirectory()&&!entry.isSymbolicLink())continue;
   try {
    const manifest=JSON.parse(fs.readFileSync(path.join(parent,entry.name,'plugin.json'),'utf8'));
    if(manifest.name!==missing.name)continue;
    const version=typeof manifest.version==='string'?manifest.version:'unknown';
    const parts=version.match(/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:\+[\w.-]+)?$/);
    found.push({status:{...missing,installed:true,version,compatible:Boolean(parts&&(Number(parts[1])>0||Number(parts[2])>=3))},parts:parts?.slice(1).map(BigInt)});
   }catch{}
  }
 }catch{}
 found.sort((a,b)=>{
  if(!a.parts||!b.parts)return Number(Boolean(b.parts))-Number(Boolean(a.parts));
  for(let i=0;i<3;i++)if(a.parts[i]!==b.parts[i])return a.parts[i]>b.parts[i]?-1:1;
  return 0;
 });
 return found[0]?.status??missing;
}
export function companionLine(status=companionStatus()) {
 if(!status.installed)return 'WARN LazyNeon core missing: routing and general guards are not active; install LazyNeon core';
 return `${status.compatible?'OK':'WARN'} Companion lazyneon ${JSON.stringify(status.version)}: ${status.compatible?'compatible':'incompatible/unknown'} (requires >=0.3.0)`;
}
