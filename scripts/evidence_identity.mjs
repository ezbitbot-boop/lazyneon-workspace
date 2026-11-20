// Evidence identity supplements filename hints. Registries are case-local and
// read-only: evidence_manifest.py output or lazy-evidence-case-v1 membership.
import fs from 'node:fs';
import path from 'node:path';

export function canonical(file) {
  try { return fs.realpathSync.native(file).normalize('NFC'); } catch {
    const parent = path.dirname(file);
    return parent === file ? file : path.join(canonical(parent), path.basename(file).normalize('NFC'));
  }
}
export function within(file, root) {
  file=file.normalize('NFC');root=root.normalize('NFC');
  file=file.toLowerCase();root=root.toLowerCase();
  const rel = path.relative(root, file);
  return rel === '' || (!rel.startsWith(`..${path.sep}`) && rel !== '..' && !path.isAbsolute(rel));
}

export function evidenceIdentity(workspace) {
  const base = workspace || process.cwd();
  const roots = [path.join(base, 'evidence')];
  const members = [];
  // Fixed discovery locations avoid recursively reading arbitrary case files.
  const discovery=[base, path.join(base,'.lazyneon-workspace'), path.join(base,'custody')];
  try {for(const e of fs.readdirSync(base,{withFileTypes:true})) if(e.isDirectory()&&!e.name.startsWith('.')) discovery.push(path.join(base,e.name,'custody'));}catch{}
  for (const dir of discovery) {
    let entries;
    try { entries = fs.readdirSync(dir); } catch { continue; }
    for (const name of entries.filter(n => /\.json$/i.test(n))) {
      const file = path.join(dir, name);
      let doc;
      try {
        if (!fs.statSync(file).isFile()) continue;
        doc = JSON.parse(fs.readFileSync(file, 'utf8'));
      } catch { continue; }
      if (doc.tool === 'case_mode.mjs init' && typeof doc.evidencePath === 'string' && Array.isArray(doc.files)) {
        const evidence = path.resolve(base, doc.evidencePath);
        try { if (fs.statSync(evidence).isDirectory()) roots.push(evidence); } catch {}
        members.push(file);
        for (const entry of doc.files) if (typeof entry.path === 'string') members.push(path.resolve(base, entry.path));
      }
      if (doc.manifest_version === 1 && typeof doc.root === 'string' && Array.isArray(doc.files)) {
        const root = path.resolve(dir, doc.root);
        roots.push(root);
        members.push(file);
        for (const entry of doc.files) if (typeof entry.path === 'string') members.push(path.resolve(root, entry.path));
      }
      if (doc.schema_version === 'lazy-evidence-case-v1' && Array.isArray(doc.items)) {
        members.push(file);
        for (const item of doc.items) if (typeof item.source?.path === 'string') members.push(path.resolve(base, item.source.path));
      }
    }
  }
  // A link inside a protected root also protects its referent. Do not recurse
  // through directory links: registering their real root handles descendants.
  function registerLinks(dir) {
    let entries;try {entries=fs.readdirSync(dir,{withFileTypes:true});}catch{return;}
    for(const entry of entries) {
      const file=path.join(dir,entry.name);
      if(entry.isSymbolicLink()) {
        try {if(fs.statSync(file).isDirectory()) roots.push(canonical(file));else members.push(canonical(file));}catch{}
      } else if(entry.isDirectory()) registerLinks(file);
    }
  }
  for(const root of [...roots]) registerLinks(root);
  const realRoots = roots.map(canonical);
  const realMembers = members.map(canonical);
  return (token) => {
    const file = path.resolve(base, String(token).replaceAll('\\', '/'));
    const real = canonical(file);
    if (roots.some(root => within(file, root)) || realRoots.some(root => within(real, root))) return true;
    if (members.some(p=>p.normalize('NFC').toLowerCase()===file.normalize('NFC').toLowerCase()) || realMembers.some(p=>p.toLowerCase()===real.toLowerCase())) return true;
    // Signatures remain recognizable after moving/renaming outside a case root.
    // Headerless raw images must be registered or retained under evidence roots.
    let fd;
    try {
      if (!fs.statSync(real).isFile()) return false;
      fd = fs.openSync(real, 'r');
      const bytes = Buffer.alloc(1024);
      const size = fs.readSync(fd, bytes, 0, bytes.length, 0);
      const header = bytes.subarray(0, size);
      return ['ElfFile\0', 'ElfChnk\0', 'EVF\t\r\n\xff\0', 'LVF\t\r\n\xff\0', 'AFF10\r\n\0', 'vhdxfile', 'PAGEDUMP', 'PAGEDU64'].some(sig => header.subarray(0, Buffer.byteLength(sig, 'latin1')).equals(Buffer.from(sig, 'latin1')))
        || header.subarray(3, 11).equals(Buffer.from('NTFS    '))
        || (size >= 1024 && header.subarray(0,4).equals(Buffer.from('FILE')) && header.readUInt16LE(4)>=40 && header.readUInt16LE(4)<512 && header.readUInt16LE(20)>=48 && header.readUInt16LE(20)<1024)
        || (size>=32 && header.subarray(0,4).equals(Buffer.from('MDMP')) && header.readUInt32LE(8)>0 && header.readUInt32LE(12)>=32)
        || (size>=512 && header.subarray(0,4).equals(Buffer.from('KDMV')) && [1,2,3].includes(header.readUInt32LE(4)));
    } catch { return false; } finally { if (fd !== undefined) fs.closeSync(fd); }
  };
}
