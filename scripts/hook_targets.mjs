/** Workspace-vendored equivalent of core hook_targets.mjs (core 4e18b95; workspace review 79026fd).
 * Input only; extends core's patch headers with Delete File and unified diffs.
 * No runtime dependency on core. Existing core/license provenance is retained.
 */
import path from 'node:path';
import {documentedReadSubcommand} from './workspace_read_registry.mjs';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {resolveWorkspace} from './hook_workspace.mjs';
import {classifyGuardResult} from './guard_verdict.mjs';
const decode = value => { try { return typeof value === 'string' ? JSON.parse(value) : value; } catch { return value; } };
export function toolInput(p) {
  p = decode(p);
  return decode(p?.toolCall?.args ?? p?.toolCall?.arguments ?? p?.toolCall?.parameters ?? p?.tool_input ?? p?.toolInput ?? p?.input ?? p?.args ?? p);
}
export function isReadOnlyTool(p) {
  let name = p?.toolCall?.name ?? p?.tool_name ?? p?.name ?? '';
  if (/^(call_mcp_tool|CallMcpTool)$/i.test(name)) { const a=toolInput(p); name=a?.tool ?? a?.tool_name ?? a?.ToolName ?? a?.toolName ?? a?.name ?? ''; }
  name = String(name).split('__').at(-1);
  if (/write|edit|replace|patch|generate|fill|redact|seal|update|delete|move/i.test(name)) return false;
  return /^(?:read|get|list|search|inspect|parse)_[a-z_]+$/i.test(name) || /^(?:read|get|list|search|inspect|read_file|read_text_file|read_document|get_file|list_files|search_files|inspect_file)$/i.test(name) || /^(ReadFile|Read|view_file|view_file_outline|view_code_item|list_dir|grep_search|find_by_name|codebase_search|parse_document|detect_format|parse_metadata|parse_pages|parse_table|compare_documents|parse_chunks|parse_form|list_resources|read_resource|query-docs|resolve-library-id)$/.test(name);
}
// Reserved core state and working journals; final deliverables are ordinary outputs.
// docs/domain-targets.md lists these formats; the regression test checks equality.
export const CORE_OWNED_PATHS = Object.freeze([
  "pins.md",
  "ulw-scope.md",
  "ulw-dag.json",
  "lookups.jsonl",
  "feedback/<name>.jsonl",
  "feedback/<name>.jsonl.<PID>.taking",
  "logs/<name>.log",
  "logs/<name>.jsonl",
  "ulw-research/<session>/brief.md",
  "ulw-research/<session>/claim-graph.md",
  "ulw-research/<session>/intent-diff.md",
  "ulw-research/<session>/observation-manifest.md",
  "ulw-research/<session>/verification-economics.md",
  "ulw-research/<session>/cause-disappearance.md",
  "ulw-research/<session>/excursion-log.md",
  "ulw-research/<session>/expansion-log.md",
  "ulw-research/<session>/sources-ledger.md",
  "ulw-research/<session>/debate-log.md",
  "ulw-research/<session>/scope.md",
  "ulw-research/<session>/plan.md",
  "ulw-research/<session>/outcome.json",
  "ulw-research/<session>/verify-*.md"
]);
const coreOwnedRE = new RegExp('(?:^|/)\\.lazyneon/(?:' + CORE_OWNED_PATHS.map(pattern =>
  pattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    .replaceAll('<session>', '[^/]+').replaceAll('<name>', '[^/]+')
    .replaceAll('<PID>', '\\d+').replaceAll('\\*', '[^/]+')
).join('|') + ')$', 'i');
export function isCoreOwned(target) {
  const owned = p => coreOwnedRE.test(p.replace(/\\/g, '/'));
  // Resolve aliases before deciding ownership; preserve the missing suffix so
  // an existing .lazyneon ancestor cannot exempt arbitrary new reports.
  let p=path.resolve(target), suffix=[];
  while (true) {
    try { return owned(path.join(fs.realpathSync(p), ...suffix)); } catch {}
    const parent=path.dirname(p);
    if(parent===p) return owned(path.resolve(target));
    suffix.unshift(path.basename(p)); p=parent;
  }
}
export function hookTargetOperations(sources) {
  const out=[];
  const workspace=sources.map(s=>resolveWorkspace(s.parsed)).find(Boolean) || process.cwd();
  const add=(v,op='write')=> {
    if(!v || v==='/dev/null') return;
    const entry={path:path.resolve(workspace,v),op}; out.push(entry); return entry;
  };
  function visit(node) {
    if(typeof node==='string') {
      const parsed=decode(node); if(parsed!==node) {visit(parsed); return;}
      let update;
      for(const m of node.matchAll(/^\*\*\* (Update File|Add File|Delete File|Move to): (.+)$/gm)) {
        const [ ,header,value]=m;
        if(header==='Move to') {
          if(update) update.op='move-src';
          add(value.trim(),'move-dst'); update=undefined;
        } else {
          const entry=add(value.trim(),header==='Delete File'?'delete':'write');
          update=header==='Update File'?entry:undefined;
        }
      }
      const paired=new Set();
      for(const m of node.matchAll(/^--- (?:a\/)?([^\r\n\t]+)[^\n]*\n\+\+\+ (?:b\/)?([^\r\n\t]+)/gm)) {
        const old=m[1].trim(), next=m[2].trim();
        paired.add(old); paired.add(next);
        if(next==='/dev/null') add(old,'delete');
        else if(old!=='/dev/null' && old!==next) {add(old,'move-src'); add(next,'move-dst');}
        else add(next);
      }
      // Preserve conservative extraction for incomplete unified headers too.
      for(const m of node.matchAll(/^(?:\+\+\+ b\/|--- a\/)([^\r\n\t]+)/gm)) {
        if(!paired.has(m[1].trim())) add(m[1].trim());
      }
      return;
    }
    if(Array.isArray(node)) {node.forEach(visit); return;}
    if(!node || typeof node!=='object') return;
    for(const [key,value] of Object.entries(node)) {
      if(/^(result|tool_result|tool_response|toolResult|toolResponse|content|text|CodeContent|Replacement)$/i.test(key)) continue;
      if(/^(file_path|filepath|AbsolutePath|path|target|target_file|targetfile|target_path|targetpath|output|output_path|outputpath|source|destination|destination_path|destinationpath|file|filename)$/i.test(key) && typeof value==='string') {
        if(key==='Target' && ('Path' in node || 'Replacement' in node)) continue;
        const v=decode(value); add(typeof v==='string'?v:value, /^source$/i.test(key)?'move-src':'write');
      } else if(/^(command|cmd|command_line|commandline|script)$/i.test(key) && typeof value==='string') {
        const shellTargets=shellWriteTargets(value,workspace);
        const verb=path.basename(shellTokens(value)[0]||'').toLowerCase();
        const simple=!/[|;&\n]/.test(value);
        for (const [i,target] of shellTargets.entries()) add(target, simple&&verb==='git'&&shellTokens(value).includes('rm')?'delete':simple&&['rm','unlink','rmdir','remove-item','del'].includes(verb)?'delete':simple&&['chmod','chown','touch'].includes(verb)?'metadata':simple&&verb==='mv'?(i===0?'move-dst':'move-src'):'write');

      } else if(value && typeof value==='object' || /^(args|arguments|tool_input|input|parameters|patch|patchText|diff)$/i.test(key)) visit(value);
    }
  }
  for(const s of sources) {
    const toolName=String(s.parsed?.toolCall?.name??s.parsed?.tool_name??'');
    if(isReadOnlyTool(s.parsed) || /^(?:mcp__|call_?mcp_?tool)/i.test(toolName) && !isWriteCapable(s.parsed)) {
      const outputs=node=>{
        node=decode(node);if(!node||typeof node!=='object')return;
        for(const [k,v] of Object.entries(node)) {
          if(/^(result|tool_result|tool_response|toolResult|toolResponse|content|text)$/i.test(k)) continue;
          if(/^(output|output_path|outputPath|destination_path|destinationPath)$/i.test(k)&&typeof v==='string') add(v);
          else if(v&&typeof v==='object'||/^(args|arguments|parameters|input)$/i.test(k)) outputs(v);
        }
      };
      outputs(toolInput(s.parsed));continue;
    }
    if(/env:(?:ANTIGRAVITY_TARGET_FILE|TARGET_FILE)/.test(s.label||'')) add(s.text);
    else visit(toolInput(s.parsed ?? s.text));
  }
  return out;
}
// PreToolUse needs every touched path, including deleted and moved sources.
export function hookTargets(sources) {
  return [...new Set(hookTargetOperations(sources).map(t=>t.path))];
}
export function contentTargets(sources) {
  return [...new Set(hookTargetOperations(sources)
    .filter(t=>t.op==='write' || t.op==='move-dst').map(t=>t.path).filter(p=>{try{return !fs.statSync(p).isDirectory();}catch{return true;}}))];
}
// Standalone guards use the same all-target dispatcher as the relay. Legacy
// transcript-only invocations retain their existing extraction path.
export function dispatchTargets(sources) {
  if(process.env.LAZYNEON_WS_SINGLE_TARGET==='1') return;
  if(!hookTargets(sources).length) return;
  const targets=contentTargets(sources);
  const workspace=sources.map(s=>resolveWorkspace(s.parsed)).find(Boolean);
  const verdicts=[];
  for(const target of targets.filter(t=>!isCoreOwned(t))) {
    const event={...(workspace?{workspacePaths:[workspace]}:{}),toolCall:{name:'write_file',args:{TargetFile:target}}};
    const r=spawnSync(process.execPath,process.argv.slice(1),{input:JSON.stringify(event),encoding:'utf8',timeout:30000,env:{...process.env,LAZYNEON_WS_SINGLE_TARGET:'1'}});
    if(r.stderr) process.stderr.write(r.stderr);
    verdicts.push(classifyGuardResult(r));
    if(r.error) console.error('[미확인] guard timeout/crash');
  }
  const status=verdicts.some(v=>v.kind==='fail')?'FAIL':verdicts.some(v=>v.kind==='unchecked')?'NOT_CHECKED':verdicts.some(v=>v.kind==='warn')?'WARN':verdicts.some(v=>v.message==='PASS')?'PASS':'NOT_APPLICABLE';
  const failed=['FAIL','NOT_CHECKED'].includes(status);
  console.log(JSON.stringify({status,...(failed?{decision:'block',reason:status==='FAIL'?'domain guard failed':'[미확인] domain guard incomplete'}:{})}));
  process.exit(failed?1:0);
}

// Tokenize without executing shell text. Quoted separators belong to arguments.
export function shellTokens(command) {
  return (command.match(/(?:"(?:\\.|[^"\\])*"|'[^']*'|[^\s"'|;&<>])+|>>?|[|;&\n]/g)||[])
    .map(t=>t.replace(/"((?:\\.|[^"\\])*)"|'([^']*)'/g,(_,a,b)=>a??b));
}
// ffmpeg writes every positional that is not an option value or an -i input,
// not only the last one (`ffmpeg -i in -y evidence/a.mp4 out.wav` writes both).
const FFMPEG_BOOLEAN=/^-(?:y|n|vn|an|sn|dn|hide_banner|nostdin|stats|nostats|re|shortest|copyts|benchmark|xerror|ignore_unknown)$/;
export function ffmpegOutputs(args) {
  const out=[];
  for(let i=0;i<args.length;i++) {
    const t=args[i];
    if(t==='-i') {i++;continue;}
    if(t.startsWith('-')&&t!=='-') {if(!FFMPEG_BOOLEAN.test(t))i++;continue;}
    out.push(t);
  }
  return out;
}
export function shellWriteTargets(command, workspace=process.cwd()) {
  const out=[];
  command=command.replace(/(<<-?\s*['"]?(\w+)['"]?[^\n]*)\n[\s\S]*?\n\2[ \t]*(?=\n|$)/g,(all,header)=>/^(?:python[\d.]*|py|node|ruby|perl)\s/m.test(command)?all:header);
  const tokens=shellTokens(command);
  const segments=[];let segment=[];
  for(let i=0;i<tokens.length;i++) {
    const t=tokens[i];
    if(t==='>'||t==='>>') {if(tokens[i+1]==='&' && /^\d+$/.test(tokens[i+2]||'')) {i+=2;continue;}if(tokens[i+1]) out.push(tokens[++i]);continue;}
    if(/^[|;&\n]$/.test(t)) {segments.push(segment);segment=[];} else segment.push(t);
  }
  segments.push(segment);
  for(const ts of segments) {
    let verb=path.basename(ts[0]||'').toLowerCase();
    if(['sudo','env','command'].includes(verb)) {ts.shift();verb=path.basename(ts[0]||'').toLowerCase();}
    const a=ts.slice(1),pos=[];let dest;
    const readSub=['lazyforensic','lazyothers'].includes(verb)?a[0]:/^(?:python[\d.]*|py|node)$/.test(verb)&&a[0]?documentedReadSubcommand(a[0],workspace):null;
    const outputVerbs=/^(?:python[\d.]*|py|node|bun|deno|lazyforensic|lazyothers|case-mode|pandoc|iconv|sort|curl|wget|ffmpeg|exiftool)$/;
    for(let i=0;i<a.length;i++) {
      const t=a[i];
      if(readSub==='integrity'&&/^--report(?:=|$)/.test(t)) {if(!t.includes('='))i++;continue;}
      if(['doc','doc-diff'].includes(readSub)&&t==='--markdown')continue;
      if(/^(?:python[\d.]*|py|iconv|sort|curl|wget|pandoc)$/.test(verb)&&/^-o.+|^--outp(?:ut)?=/.test(t)) {out.push(t.startsWith('-o')?t.slice(2):t.split('=').slice(1).join('='));continue;}
      if(outputVerbs.test(verb)&&t==='--outp') {out.push(a[++i]);continue;}
      if((outputVerbs.test(verb)&&/^(?:-o|--output|--out|--markdown|--session-dir|--out-dir|--outdir|--report|--vault|--plot-fft|--events-out|--output-md|--output-json|--export-axiom-counts)$/.test(t)) || /^(?:--output|--out|--markdown|--session-dir|--out-dir|--outdir|--report|--vault|--plot-fft|--events-out|--output-md|--output-json|--export-axiom-counts)=/.test(t)) {
        out.push(t.includes('=')?t.slice(t.indexOf('=')+1):a[++i]);continue;
      }
      if(['cp','mv','install','rsync'].includes(verb)&&/^(?:-t|--target-directory)(?:=|$)/.test(t)) {dest=t.includes('=')?t.split('=').slice(1).join('='):a[++i];continue;}
      if(verb==='dd'&&t.startsWith('of=')) out.push(t.slice(3));
      if(verb==='copy-item'&&/^-(?:Path|LiteralPath)$/i.test(t)) {pos.push(a[++i]);continue;}
      if(verb==='copy-item'&&/^-Destination$/i.test(t)) {dest=a[++i];continue;}
      if(['set-content','add-content','out-file','move-item'].includes(verb)&&/^-(?:Path|LiteralPath|FilePath|Destination)$/i.test(t)) {out.push(a[++i]);continue;}
      if(t.startsWith('-')) continue;
      pos.push(t);
    }
    if(['cp','mv','install','rsync','ditto','copy-item'].includes(verb)) {
      const sources=dest?pos:pos.slice(0,-1);dest=dest||pos.at(-1);
      if(dest) {
        let directory=dest.endsWith('/');try{directory ||= fs.statSync(path.resolve(workspace,dest)).isDirectory();}catch{}
        out.push(...(directory?sources.map(src=>path.join(dest,path.basename(src))):[dest]));
      }
      if(verb==='mv') out.push(...sources);
    }
    if(['rm','unlink','rmdir','mkdir','touch','chmod','chown','truncate','tee','remove-item','del','erase','ri','rd'].includes(verb)) out.push(...pos);
    if(['set-content','add-content','out-file'].includes(verb) && !a.some(t=>/^-(?:Path|LiteralPath|FilePath)$/i.test(t))) out.push(pos[0]);
    if(verb==='cmd'&&a[0]?.toLowerCase()==='/c') out.push(...shellWriteTargets(a.slice(1).join(' '),workspace));
    if(verb==='wevtutil'&&['epl','cl'].includes(a[0])) out.push(...pos.slice(1));
    if(verb==='sed'&&a.some(t=>t==='--in-place'||/^-i/.test(t))) {
      const rest=[];let expression=false;
      for(let i=0;i<a.length;i++) {const t=a[i];if(t==='-i'&&a[i+1]===''){i++;continue;}if(t==='-e'||t==='-f'){i++;expression=true;continue;}if(t.startsWith('-'))continue;if(!expression){expression=true;continue;}rest.push(t);}
      out.push(...rest);
    }
    if(verb==='perl'&&a.some(t=>/^-[a-z]*i/.test(t)))out.push(...pos.slice(1));
    if(verb==='rg'&&a.some(t=>/^--pre(?:=|$)/.test(t))) out.push(...pos);
    if(verb==='exiftool'&&!a.includes('-o')&&a.some(t=>/^-[\w:]+[+-]?=|^-geotag$|^-@$|^-tagsfromfile$|^-[\w:]+</i.test(t))) out.push(...pos);
    if(verb==='tar'&&a.some(t=>/^-[^-]*x|^--extract$/.test(t))) {
      const i=a.findIndex(t=>t==='-C'||t==='--directory');out.push(i>=0?a[i+1]:(a.find(t=>t.startsWith('--directory='))||'').slice(12)||'.');
    }
    if(verb==='unzip') {const i=a.indexOf('-d');out.push(i>=0?a[i+1]:'.');}
    if(verb==='git'&&a.includes('config')) {
      const i=a.findIndex(t=>t==='--file'||t==='-f');const eq=a.find(t=>t.startsWith('--file='));
      if(!a.some(t=>/^(?:--get|--get-all|--list|-l)$/.test(t))) out.push(i>=0?a[i+1]:eq?eq.slice(7):'.git/config');
    }
    if(verb==='git'&&a.some(t=>/^(?:checkout|restore|reset|clean|rm|mv|apply)$/.test(t))) {
      const wt=a.find(t=>t.startsWith('--work-tree='));
      const sub=a.findIndex(t=>/^(?:checkout|restore|reset|clean|rm|mv|apply)$/.test(t));
      const sep=a.indexOf('--',sub);
      const paths=(sep>=0?a.slice(sep+1):a.slice(sub+1)).filter(t=>!t.startsWith('-'));
      out.push(...(wt?[wt.slice(12)]:paths.length?paths:['.']));
    }
    if(verb==='ffmpeg') out.push(...ffmpegOutputs(a));
    const piiInput=['lazyforensic','lazyothers'].includes(verb)&&a.includes('pii')?a[a.indexOf('pii')+1]:/^(?:python[\d.]*|py)$/.test(verb)&&path.basename(pos[0]||'')==='pii_mask.py'?pos[1]:null;
    if(piiInput && a.includes('--mask') && (a.includes('--in-place') || !a.some(t=>['-o','--output'].includes(t)||t.startsWith('--output=')))) {
      let directory=false;try {directory=fs.statSync(path.resolve(workspace,piiInput)).isDirectory();}catch{}
      out.push(a.includes('--in-place')||directory?piiInput:path.join(path.dirname(piiInput),path.parse(piiInput).name+'.masked'+path.extname(piiInput)));
    }
    if (/^(?:python[\d.]*|py|node)$/.test(verb) && !a.some(t=>/^-[cem]$|^--eval$/.test(t))) {
      const script=pos[0]||'';
      const documented=documentedReadScript(script,workspace);
      const claims=path.basename(script)==='report-tools.mjs' && a.includes('--from') && a.includes('--session-dir');
      if(!documented && !claims && !out.length) out.push(...pos.slice(1).filter(t=>/[\/.]/.test(t)));
    }
    // Inline interpreter writes: literals passed to filesystem mutators.
    if(/^(?:python[\d.]*|py|node|bun|deno|ruby|perl|php|powershell|pwsh)$/.test(verb)) {
      for(const m of command.matchAll(/(?:open|writeFile(?:Sync)?|appendFile(?:Sync)?|unlink(?:Sync)?|remove|rename|WriteAllText|WriteAllBytes)\s*\(\s*['"]([^'"]+)['"]\s*(?:,\s*(?:mode\s*=\s*)?['"]([^'"]*)['"])?/g)) {
        if(!m[0].startsWith('open')||/[wax+]/.test(m[2]||'')) out.push(m[1]);
      }
      for(const m of command.matchAll(/(?:rename|replace|move)\s*\(\s*['"]([^'"]+)['"]\s*,\s*['"]([^'"]+)['"]/g)) out.push(m[1],m[2]);
      for(const m of command.matchAll(/Path\s*\(\s*['"]([^'"]+)['"]\s*\)\s*\.(?:rename|replace)\s*\(\s*['"]([^'"]+)['"]/g)) out.push(m[1],m[2]);
      for(const m of command.matchAll(/Path\s*\(\s*['"]([^'"]+)['"]\s*\)\s*\.open\s*\(\s*(?:mode\s*=\s*)?['"]([^'"]+)['"]/g)) if(/[wax+]/.test(m[2])) out.push(m[1]);
      for(const m of command.matchAll(/(?:Path\s*\(\s*)['"]([^'"]+)['"]\s*\)\s*\.(?:write_text|write_bytes|unlink|rename)\s*\(/g)) out.push(m[1]);
    }
  }
  if(/\.(?:Delete|MoveTo|WriteAllText|WriteAllBytes)\s*\(|::WriteAll(?:Text|Bytes)\s*\(|\b(?:ri|move|Remove-Item)(?:\s|$)/i.test(command)) {
    for(const m of command.matchAll(/["']([^"']+)["']|([A-Za-z]:\\[^\s(){}]+|[^\s(){}]+[\/]evidence[\/][^\s(){}]+)/g)) out.push(m[1]||m[2]);
    for(const m of command.matchAll(/\b(?:ri|move|Remove-Item)\s+([^\s(){}]+)/gi)) out.push(m[1]);
  }
  return [...new Set(out.filter(Boolean))];
}
export function isWriteCapable(p) {
  if(isReadOnlyTool(p)) return false;
  const input=toolInput(p);let name=String(p?.toolCall?.name??p?.tool_name??'');
  if(/call_?mcp_?tool/i.test(name)) name=input?.tool??input?.tool_name??input?.ToolName??input?.toolName??input?.name??name;
  const command=input?.CommandLine??input?.command??input?.cmd??'';
  if(command) {
    const tokens=shellTokens(command), verb=path.basename(tokens[0]||'');
    if(/^(?:python[\d.]*|py|node)$/.test(verb) && tokens[1] && !tokens[1].startsWith('-') && !documentedReadScript(tokens[1],resolveWorkspace(p)||process.cwd())) return true;
    return shellWriteTargets(command).length>0 || /\b(?:cp|mv|rm|tee|dd|install|rsync|Set-Content|Out-File)\b|\.(?:write|unlink|remove)|\bopen\([^)]*,\s*['"][wax]/i.test(command);
  }
  return /write|edit|patch|replace|generate|fill|redact|seal|delete|move|update/i.test(name);
}

export function unresolvedShellWrite(command) {
  return /\b(?:powershell|pwsh)(?:\.exe)?\b[^|&;\n]*\s-(?:e|ec|en\w*)(?=\s|$)/i.test(command)
    || /\$\([^)]*\b(?:rm|mv|cp|del|ri)\b/.test(command)
    || /(?:\.write(?:File|_text|_bytes)?|\bopen)\s*\([^)]*(?:['"][wax]|write)/.test(command) && !shellWriteTargets(command).length;
}

function documentedReadScript(script,workspace) {
  return Boolean(documentedReadSubcommand(script,workspace));
}
