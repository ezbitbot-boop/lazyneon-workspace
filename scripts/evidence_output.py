"""Shared output boundary: declared evidence roots are never output directories."""
import json
import ntpath
import os
import tempfile
from pathlib import Path
import unicodedata


def identity(p):
    # Normalize foreign Windows paths for portable boundary checks as well.
    raw = str(p)
    if ntpath.isabs(raw) and (ntpath.splitdrive(raw)[0] or '\\' in raw):
        resolved = str(Path(p).resolve()) if os.name == 'nt' else ntpath.normpath(raw)
        raw = resolved.replace('\\', '/')
    else:
        raw = str(Path(p).resolve())
    return unicodedata.normalize('NFC', raw.replace('\\', '/')).casefold()


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
    if _inode_collides(output, roots, members):
        raise ValueError(f'Output is the same file (hard link) as evidence: {output}; use a new path in the case working folder')
    return output


def _file_key(p):
    try:
        st = os.stat(p)
    except OSError:
        return None
    return (st.st_dev, st.st_ino)


def _inode_collides(output, roots, members):
    # A path check alone misses a hard link to evidence placed outside it.
    key = _file_key(output)
    if key is None:
        return False
    if any(_file_key(p) == key for p in members):
        return True
    for root in roots:
        if not os.path.isdir(root):
            continue
        for d, _dirs, files in os.walk(root):
            if any(_file_key(os.path.join(d, f)) == key for f in files):
                return True
    return False


def atomic_write(path, data, mode=None):
    """Write to a temp file beside path, then rename over it.

    The rename replaces the directory entry, so an existing hard link to
    another file is never written through. mode=None keeps the umask default.
    """
    path = Path(path)
    if mode is None:
        umask = os.umask(0)
        os.umask(umask)
        mode = 0o666 & ~umask
    fd, tmp = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=str(path.parent or '.'))
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
