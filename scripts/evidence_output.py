"""Shared output boundary: declared evidence roots are never output directories."""
import json
from pathlib import Path
import unicodedata


def identity(p):
    return unicodedata.normalize('NFC', str(Path(p).resolve())).casefold()


def within(p, root):
    p, root = identity(p), identity(root)
    return p == root or p.startswith(root.rstrip('/') + '/')


def registries():
    # Fixed locations in cwd/ancestors and immediate case children; never walk evidence.
    seen = set()
    for base in [Path.cwd(), *Path.cwd().parents]:
        dirs = [base, base/'.lazyneon-workspace', base/'custody']
        if base == Path.cwd() or base == Path.cwd().parent:
            dirs += [child/'custody' for child in base.iterdir() if child.is_dir() and not child.is_symlink()]
        for d in dirs:
            for p in d.glob('*.json'):
                if p in seen: continue
                seen.add(p)
                try:
                    doc=json.loads(p.read_text(encoding='utf-8'))
                    if isinstance(doc,dict): yield p,doc
                except (OSError,ValueError): pass


def working_folder(inputs=()):
    candidates = set()
    for p,doc in registries():
        if doc.get('tool') != 'case_mode.mjs init': continue
        if within(Path.cwd(),doc['caseDir']): return Path(doc['caseDir'])
        if within(Path.cwd(),doc['evidencePath']) or any(within(source,doc['evidencePath']) for source in inputs):
            candidates.add(doc['caseDir'])
    if len(candidates) == 1: return Path(candidates.pop())
    if len(candidates) > 1: raise ValueError('Multiple cases reference this evidence; specify an output folder')
    return Path.cwd()


def safe_output(value, inputs=()):
    output=Path(value).absolute()
    roots=[Path.cwd()/'evidence']
    members=[]
    for source in inputs:
        if not source: continue
        source=Path(source)
        (roots if source.is_dir() else members).append(source)
    for p,doc in registries():
        if doc.get('manifest_version')==1 and doc.get('root'):
            roots.append(p.parent/doc['root'])
        if doc.get('tool')=='case_mode.mjs init':
            source=Path(doc['evidencePath'])
            (roots if source.is_dir() else members).append(source)
            members.extend(Path(f['path']) for f in doc.get('files',[]))
    if any(within(output,r) for r in roots) or any(identity(output)==identity(p) for p in members):
        raise ValueError(f'Output must be outside evidence: {output}; use the case working folder')
    return output
