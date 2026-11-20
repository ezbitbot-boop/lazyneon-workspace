// Secondary policy: unknown programs/flags referencing evidence fail closed.
import path from 'node:path';
import {readFlags,documentedReadSubcommand} from './workspace_read_registry.mjs';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {shellTokens, toolInput, shellWriteTargets} from './hook_targets.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
export function shellCommands(sources) {
  const out=[];
  function visit(v) {
    if(!v || typeof v!=='object') return;
    for(const [k,x] of Object.entries(v)) {
      if(/^(command|cmd|command_line|commandline|script)$/i.test(k)&&typeof x==='string')out.push(x);
      else if(/^(args|arguments|input|parameters|tool_input)$/i.test(k)) {
        try {visit(typeof x==='string'?JSON.parse(x):x);}catch{}
      }
    }
  }
  for(const s of sources) visit(toolInput(s.parsed));
  return out;
}
export function evidenceTokens(command) {
  // Data fed to cat is not a command or a filename operand. Keep executable
  // interpreter heredocs visible to the conservative evidence check.
  if (/^\s*cat\s+<</.test(command)) command=command.replace(/(<<-?\s*['"]?(\w+)['"]?[^\n]*)\n[\s\S]*?\n\2[ \t]*(?=\n|$)/g,'$1');
  // Only Python import statements are module references; quoted filenames and
  // every other expression remain visible (including writes after an import).
  command=command.replace(/(\bpython[\d.]*\s+-c\s+)(["'])([\s\S]*?)\2/g,(_,prefix,quote,code)=>
    prefix+quote+code.replace(/(^|[;\n])([ \t]*(?:import|from)\s+)[a-z_]\w*(?:\.[a-z_]\w*){2,}(?=\s|;|$)/g,'$1$2MODULE')+quote);
  const quoted=[...command.matchAll(/"([^"\n]+)"|'([^'\n]+)'/g)].map(m=>m[1]??m[2]);
  return [...quoted,...shellTokens(command),...command.split(/[\s"'`(){}[\],;<>|]+/)].flatMap(t=>[t,...t.split('=')]).filter(Boolean);
}
const simple={
 type:/^$/, dir:/^\/(?:[abswqndlr]+|o(?::[a-z-]+)?|t:[acw])$/i,
 findstr:/^\/(?:[bceilnmoprsuvx]+|c:.*)$/i, more:/^[-/][desp]+$/i,
 iconv:/^-(?:[fcto]|-(?:from-code|to-code|output)(?:=.*)?)$/,
 sort:/^-(?:[bcdfgimnruVh]+|[ktT]|-(?:numeric-sort|reverse|unique|stable|field-separator|key|output)(?:=.*)?)$/,
 uniq:/^-(?:[cdiuz]+|[fsw]|-(?:count|repeated|unique|ignore-case)(?:=.*)?)$/,
 cut:/^-(?:[bcdfsn]+|-(?:bytes|characters|delimiter|fields|complement|only-delimited|output-delimiter)(?:=.*)?)$/,
 cat:/^-(?:[benstuvAET]+|-(?:number|number-nonblank|show-all|show-ends|show-tabs|squeeze-blank))$/,
 less:/^-(?:[FINRSXKMQ]+|-(?:quit-if-one-screen|IGNORE-CASE|LINE-NUMBERS|RAW-CONTROL-CHARS|no-init))$/,
 head:/^-(?:[ncqv]|\d+|-(?:lines|bytes|quiet|verbose)(?:=\d+)?)$/,
 tail:/^-(?:[ncfFqv]|\d+|-(?:lines|bytes|follow|quiet|verbose)(?:=\w+)?)$/,
 wc:/^-(?:[clmwL]+|-(?:bytes|chars|lines|words|max-line-length))$/,
 ls:/^-(?:[aAbBcCdDfFgGhHiIkLlLmMnNoOpqQrRsStTuUvVwWxX1]+|-(?:all|almost-all|directory|human-readable|numeric-uid-gid|recursive|size|inode|color(?:=\w+)?))$/,
 stat:/^-(?:[fLtqx]|-(?:format|printf)(?:=.*)?)$/,
 file:/^-(?:[bikLNz]+|-(?:mime|mime-type|mime-encoding|brief|dereference))$/,
 strings:/^-(?:[aAdfnotx]+|n|\d+|-(?:all|print-file-name|bytes)(?:=\d+)?)$/,
 xxd:/^-(?:[abcegilpsuv]|\d+)$/,
 hexdump:/^-(?:[bcCdovx]|[ens])$/,
 grep:/^-(?:[aAbBcDEeFfGHIhilLmnoPqRrsUVvwxZz0-9]+|-(?:color|binary-files|exclude|include|exclude-dir|context|after-context|before-context)(?:=.*)?)$/,
 rg:/^-(?:[aAbBcCeFfHhIiLlMmNnOoPpQqSstTUuVvwxz0-9]+|-(?:files|hidden|no-ignore|line-number|count|files-with-matches|only-matching|glob|iglob|type|type-not|encoding|color|context|after-context|before-context|json|stats|no-heading|heading|sort|sortr)(?:=.*)?)$/,
};
export function readOnlyEvidenceCommand(command,workspace,isProtected) {
  // These preambles only select text encoding; all remaining statements must
  // still form a single allowlisted read pipeline.
  command=command.split(/\r?\n|;/).filter(s=>!/^\s*(?:\[Console\]::(?:Output|Input)Encoding\s*=\s*[\w.:\[\]()]+|\$OutputEncoding\s*=\s*[\w.:\[\]()]+|chcp(?:\.com)?\s+65001(?:\s*>\s*\$null)?|\$env:PYTHON(?:UTF8|IOENCODING)\s*=\s*['"]?[\w-]+['"]?)\s*$/i.test(s)).join(';').trim();
  // A property lookup on one read command is safe; method calls stay rejected.
  if (/^\([^()]*\)(?:\.\w+)*$/.test(command)) command=command.replace(/^\(([^()]*)\)(?:\.\w+)*$/,'$1');
  // No substitutions, nested shells, or command chains. Ordinary pipelines are
  // accepted only when every component is in the read-only table.
  if(/[`]|\$\(|[{}]/.test(command)) return false;
  if(shellWriteTargets(command,workspace).some(isProtected)) return false;
  command=command.replace(/\b[12]?>&[12]\b/g,'');
  const segments=splitReadSegments(command);
  return segments.every(segment=> {
    const ts=shellTokens(segment), clean=[];
    for(let i=0;i<ts.length;i++) {
      if(ts[i]==='>'||ts[i]==='>>') {if(!ts[i+1]||isProtected(ts[++i]))return false;continue;}
      clean.push(ts[i]);
    }
    let [program,...args]=clean;
    if(/^(?:cmd|cmd.exe)$/i.test(program||'')&&args[0]?.toLowerCase()==='/c') {args.shift();program=args.shift();}
    if(!program) return false;
    program=path.basename(program).replace(/\.exe$/i,'').toLowerCase();
    const flags=args.filter(t=>t.startsWith('-')&&t!=='--');
    if(['python','python3','python3.12','py','node'].includes(program)) {
      const script=args.shift();if(!script||script.startsWith('-'))return false;
      const normalizedScript=script.replaceAll('\\','/');
      const base=path.basename(normalizedScript);
      if(base==='report-tools.mjs'&&args[0]==='claims'&&args[1]==='snapshot'&&args.includes('--session-dir')) return true;
      const sub=documentedReadSubcommand(script,workspace);
      return Boolean(sub&&workspaceRead(sub,args));
    }
    if(['lazyforensic','lazyothers'].includes(program))return workspaceRead(args.shift(),args);
    if(program==='case-mode')return workspaceRead('case-mode',args);
    if(['cp','ditto','rsync','copy-item'].includes(program)) {
      const operands=args.filter(a=>!a.startsWith('-'));
      return operands.length>=2 && !isProtected(operands.at(-1)) && flags.every(f=>/^(?:-[aRpPfv]+|--archive|-Path|-LiteralPath|-Destination|-Recurse|-Force)$/i.test(f));
    }
    if(program==='certutil')return args.length>=2&&args[0].toLowerCase()==='-hashfile'&&flags.length===1;
    if(['icacls','attrib'].includes(program))return args.length===1&&!/^[-+]|^\/(?:grant|deny|reset|remove|inheritance|setowner|restore|save|[sdl])(?:$|:)/i.test(args[0]);
    if(program==='tesseract')return args[1]==='stdout'&&flags.every(f=>['-l','--psm','--oem','--dpi'].includes(f))&&args.every((a,i)=>i<2||a.startsWith('-')||args[i-1]?.startsWith('-'));
    if(program==='ffmpeg')return args.includes('-i')&&!isProtected(args.at(-1))&&flags.every(f=>/^-(?:i|t|ss|to|vn|an|ar|ac|c(?::[av])?|codec(?::[av])?|f|y|n|hide_banner|loglevel)$/.test(f));
    if(program==='git')return /^(status|log|diff|show|ls-files|ls-tree|rev-parse)$/.test(args[0]||'') && flags.every(f=>/^-(?:[pUsw]|-(?:short|porcelain|stat|numstat|name-only|name-status|oneline|no-patch|no-ext-diff|no-textconv|cached|staged|all|pretty(?:=.*)?|format=.*))$/.test(f));
    if(program==='xxd') {
      const operands=[];for(let i=0;i<args.length;i++){if(/^-[cegls]$/.test(args[i])){i++;continue;}if(!args[i].startsWith('-'))operands.push(args[i]);}
      if(operands.length>1)return false;
    }
    if(program==='sqlite3')return args.includes('-readonly') && flags.every(f=>['-readonly','-json','-csv','-header','-noheader','-list'].includes(f)) && !args.some(a=>/\.|\b(?:attach|load_extension|writefile|vacuum)\b/i.test(a) && a!==args.find(t=>!t.startsWith('-'))) && !args.some(a=>/^\s*\./.test(a));
    if(program==='exiftool')return flags.every(f=>/^-(?:j|json|G\d*|g\d*|a|s\d*|n|b|u|r|q|fast\d*|orientation|FileName|FileSize|FileType|DateTimeOriginal|CreateDate|ModifyDate|GPSLatitude|GPSLongitude)$/i.test(f));
    if(program==='ffprobe')return flags.every(f=>/^-(?:v|loglevel|print_format|of|show_(?:format|streams|entries|frames|packets|chapters|programs|error)|select_streams|count_frames|count_packets|read_intervals|i|hide_banner)$/.test(f));
    if(program==='find')return flags.every(f=>/^-(?:name|iname|path|ipath|type|size|mtime|atime|ctime|maxdepth|mindepth|print|print0|ls|a|o|not|L|P|H)$/.test(f));
    if(/^(?:sha(?:1|224|256|384|512)sum|shasum|md5sum|md5)$/.test(program))return flags.every(f=>/^-(?:[abctwqrs]+|-(?:binary|text|check|tag|quiet|status|strict|warn|algorithm)(?:=\d+)?)$/.test(f));
    if(['out-null','out-string','measure-object','select-object','format-list','format-table'].includes(program))return !/[(){}$`]|::/.test(segment)&&flags.every(f=>/^-(?:First|Last|Skip|Property|ExpandProperty|Sum|Average|Minimum|Maximum|Line|Word|Character|AutoSize|Wrap|Width)$/i.test(f));
    if(program==='out-file')return args.length===1&&!isProtected(args[0]);
    if(['get-filehash','get-item','get-childitem','get-content','test-path','select-string','get-winevent','get-acl'].includes(program))return !/[(){}]|::/.test(segment)&&flags.every(f=>/^-(?:Path|LiteralPath|Algorithm|Recurse|Filter|Name|Raw|TotalCount|Tail|Pattern|List|Force|ErrorAction|Oldest|Encoding)$/i.test(f));
    return Boolean(simple[program] && flags.every(f=>simple[program].test(f)));
  });
}
function workspaceRead(sub,args) {
  const flags=args.filter(t=>t.startsWith('-'));
  if(sub==='triage')sub='scan';
  if(sub==='case-mode') {
    if(['unlock','lock'].includes(args[0])) {const i=args.indexOf('--reason');return i>=0&&Boolean(args[i+1]?.trim())&&!args[i+1].startsWith('-')&&flags.every(f=>['--case','--manifest','--journal','--reason'].includes(f));}
    return ['init','close','verify'].includes(args[0])&&flags.every(f=>/^--(?:out|case)(?:=|$)/.test(f));
  }

  return Boolean(readFlags[sub]&&flags.every(f=>readFlags[sub].includes(f.split('=')[0])));
}

function splitReadSegments(command) {
  const segments=[];let current='',quote=null;
  for(let i=0;i<command.length;i++) {
    const c=command[i];
    if(quote) {current+=c;if(c===quote)quote=null;continue;}
    if(c==='"'||c==="'"){quote=c;current+=c;continue;}
    if(c==='|'||c===';'||c==='\n'||c==='&') {
      if(c==='&'&&command[i+1]!=='&')return [''];
      if(command[i+1]===c)i++;
      if(!current.trim())return [''];segments.push(current);current='';
    }else current+=c;
  }
  if(quote)return [''];
  segments.push(current);return segments;
}
