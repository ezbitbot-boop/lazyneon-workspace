"""OS evidence write protection. Never elevates privileges; records actual mechanisms."""
try:
    from scripts.workspace_provenance import workspace_provenance
except ModuleNotFoundError:
    from workspace_provenance import workspace_provenance

# One execution identity for the entire protection operation, including large journals.
_WORKSPACE_PROVENANCE = workspace_provenance()
import json
import re
import copy
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

# icacls specific rights only. The simple rights W and D include SYNCHRONIZE, so denying
# them also blocks reading and listing. WD/AD: write data/append (a directory: add file/
# subdirectory); WEA/WA: extended attributes and attributes, so the read-only attribute
# cannot be cleared; DE/DC: delete, rename, move out, delete child.
WINDOWS_DENY = ('WD', 'AD', 'WEA', 'WA', 'DE', 'DC')


def command(*args):
    return subprocess.run(args, capture_output=True, text=True)


def checked(*args):
    result = command(*args)
    if result.returncode:
        raise PermissionError(f"{' '.join(args)}: {result.stderr or result.stdout}")
    return result.stdout

# NTFS file IDs exceed 2**53; the record passes through Node (case_mode.mjs), whose JSON
# numbers would round them and every later identity check would fail. Store decimal strings.
def identity(s):
    return str(s.st_dev), str(s.st_ino)


def same_identity(s, e):
    return identity(s) == (str(e.get('dev')), str(e.get('ino')))


def read_only_media(p):
    if os.name != 'nt':
        return bool(os.statvfs(p).f_flag & os.ST_RDONLY)
    import ctypes
    volume = ctypes.create_unicode_buffer(32768)
    if not ctypes.windll.kernel32.GetVolumePathNameW(str(p), volume, len(volume)):
        raise ctypes.WinError()
    flags = ctypes.c_ulong()
    if not ctypes.windll.kernel32.GetVolumeInformationW(volume.value, None, 0, None, None, ctypes.byref(flags), None, 0):
        raise ctypes.WinError()
    return bool(flags.value & 0x80000)  # FILE_READ_ONLY_VOLUME


def journal_event(journal, event, **data):
    if journal is None:
        return
    with open(journal, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'event': event, **data, 'workspace_provenance': _WORKSPACE_PROVENANCE}) + '\n')
        f.flush()
        os.fsync(f.fileno())


def protect(paths, journal=None):
    entries = []
    seen = set()
    for value in paths:
        root = Path(value).absolute()
        for p in [root, *sorted(root.rglob('*'))] if root.is_dir() else [root]:
            if str(p) in seen:
                continue
            seen.add(str(p))
            s = p.lstat()
            if p.is_symlink() or not (p.is_dir() or p.is_file()):
                raise ValueError(f'Unsupported evidence entry: {p}')
            if p.is_file() and s.st_nlink > 1:
                raise ValueError(f'Hard-linked evidence unsupported: {p}')
            dev, ino = identity(s)
            entries.append({'path': str(p), 'mode': stat.S_IMODE(s.st_mode), 'dev': dev,
                            'ino': ino, 'original_flags': getattr(s, 'st_flags', 0), 'applied': []})
    # An existing matching lock record owns the pre-lock mode/flags. Inherit
    # that recovery state rather than treating already locked modes as original.
    from evidence_output import registries
    originals = {}
    for _, doc in registries():
        previous = doc.get('protection') or {}
        if previous.get('platform') == sys.platform:
            for old in previous.get('entries', []):
                originals[(old.get('path'), str(old.get('dev')), str(old.get('ino')))] = old
    for e in entries:
        old = originals.get((e['path'], e['dev'], e['ino']))
        if old:
            e['mode'] = old['mode']
            e['original_flags'] = old.get('original_flags', 0)
            for key in ('original_acl_hex', 'user'):
                if key in old: e[key] = old[key]
    record = {'platform': sys.platform, 'entries': entries, 'notes': []}
    # Entire recovery record is durable before the first mutation. Subsequent
    # intent rows make interrupted operations recoverable even before completion.
    journal_event(journal, 'prepared', record=record)
    rollback = copy.deepcopy(record)
    rollback_entries = {e['path']: e for e in rollback['entries']}
    for e in rollback['entries']:
        current = Path(e['path']).lstat()
        e['mode'] = stat.S_IMODE(current.st_mode)
        e['original_flags'] = getattr(current, 'st_flags', 0)
    try:
        for e in reversed(entries):
            p = Path(e['path'])
            if read_only_media(p):
                e['status'] = 'protected-by-media'
                journal_event(journal, 'protected', entry=e)
                continue
            def apply(name, fn, observed):
                journal_event(journal, 'intent', path=str(p), mechanism=name, entry=e)
                e['applied'].append(name)  # rollback even if mutation partially fails
                try:
                    if not observed(): fn()
                except OSError as exc:
                    import errno
                    if exc.errno not in (errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS):
                        raise
                if not observed():
                    e['applied'].remove(name)
                journal_event(journal, 'applied', entry=e)
            apply('chmod a-w', lambda: p.chmod(e['mode'] & ~0o222), lambda: not p.lstat().st_mode & 0o222)
            if sys.platform == 'darwin':
                apply('uchg', lambda: os.chflags(p, p.lstat().st_flags | stat.UF_IMMUTABLE),
                      lambda: bool(p.lstat().st_flags & stat.UF_IMMUTABLE))
            elif os.name == 'nt':
                user = checked('whoami').strip()
                e['user'] = user
                with tempfile.TemporaryDirectory(prefix='evidence-acl-') as temp:
                    saved = Path(temp)/'acl.txt'
                    checked('icacls', str(p), '/save', str(saved))
                    rollback_entries[str(p)]['original_acl_hex'] = saved.read_bytes().hex()
                    e.setdefault('original_acl_hex', saved.read_bytes().hex())
                apply('attrib +R', lambda: checked('attrib', '+R', str(p)),
                      lambda: bool(p.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY))
                apply('deny-write ACL', lambda: checked('icacls', str(p), '/deny', f"{user}:({','.join(WINDOWS_DENY)})"),
                      lambda: acl_present(e))
            elif sys.platform.startswith('linux'):
                journal_event(journal, 'intent', path=str(p), mechanism='chattr +i', entry=e)
                if shutil.which('chattr') and command('chattr', '+i', str(p)).returncode == 0:
                    e['applied'].append('chattr +i')
            e['status'] = 'protected' if e['applied'] else 'not-lockable'
            # Windows needs both: the deny ACE names only the current user, while the
            # read-only attribute makes DeleteFile refuse every caller.
            locked = {'uchg', 'chattr +i'} & set(e['applied']) or {'deny-write ACL', 'attrib +R'} <= set(e['applied'])
            if not locked:
                e['status'] = 'not-lockable'
                record['notes'].append(f"{p}: not lockable by immutable flag/ACL; applied: {e['applied']}")
            journal_event(journal, 'protected', entry=e)
        journal_event(journal, 'complete')
        return record
    except BaseException:
        for e in entries:
            rollback_entries[e['path']]['applied'] = e['applied']
            rollback_entries[e['path']]['status'] = e.get('status')
        unlock(rollback, strict=False)  # best-effort rollback; keep the original error
        journal_event(journal, 'rolled-back')
        raise


def acl_present(e):
    """True when the recorded user holds an explicit deny ACE with exactly WINDOWS_DENY."""
    ace = re.compile(r'(?:^|\s)' + re.escape(e['user']) + r':((?:\([^)]*\))+)\s*$', re.IGNORECASE)
    for line in checked('icacls', e['path']).splitlines():
        match = ace.search(line)
        if match:
            flags = re.findall(r'\(([^)]*)\)', match.group(1))
            if flags[:-1] == ['DENY'] and set(flags[-1].split(',')) == set(WINDOWS_DENY):
                return True
    return False


def lock(record, journal=None):
    if record.get('platform') != sys.platform:
        raise ValueError('Unlock/relock must run on the recorded OS')
    # Do not replace the baseline identities or original modes when relocking.
    for e in record['entries']:
        s = Path(e['path']).lstat()
        if stat.S_ISLNK(s.st_mode) or not same_identity(s, e):
            raise ValueError('PROTECTION identity changed: ' + e['path'])
    fresh = protect([e['path'] for e in record['entries']], journal=journal)
    missing = verify(record)
    if missing:
        unlock(fresh)
        raise ValueError('; '.join(missing))
    return fresh


def recovery_record(journal):
    record = None
    entries = {}
    with open(journal, encoding='utf-8') as source:
        for line in source:
            try:
                row = json.loads(line)
            except ValueError:
                break  # interrupted final append; preceding durable intent remains
            if row['event'] == 'prepared':
                record = row['record']
                entries = {e['path']: e for e in record['entries']}
            if row.get('entry'):
                entry = row['entry']
                entries[entry['path']] = entry
                if row['event'] == 'intent' and row['mechanism'] not in entry['applied']:
                    entry['applied'].append(row['mechanism'])
    if record is None:
        raise ValueError('No prepared protection record in journal')
    record['entries'] = list(entries.values())
    return record


def unlock(record, strict=True):
    if record.get('platform') != sys.platform:
        raise ValueError('Unlock must run on the recorded OS')
    # Like lock/verify, check every identity before changing anything: a
    # replacement file at a recorded path must not receive the recorded mode.
    problems, targets = [], []
    for e in record['entries']:
        p = Path(e['path'])
        if e.get('status') == 'protected-by-media' or not e.get('applied'):
            continue
        try:
            s = p.lstat()
        except FileNotFoundError:
            problems.append(f'missing: {p}')
            continue
        if stat.S_ISLNK(s.st_mode) or ('dev' in e and 'ino' in e and not same_identity(s, e)):
            problems.append(f'identity changed: {p}')
            continue
        targets.append(e)
    if problems and strict:
        raise ValueError('UNLOCK incomplete (복구 불완전), nothing changed: ' + '; '.join(problems))
    for e in targets:
        p = Path(e['path'])
        if 'uchg' in e['applied']: os.chflags(p, e.get('original_flags', 0))
        if 'chattr +i' in e['applied']: checked('chattr', '-i', str(p))
        if 'deny-write ACL' in e['applied']:
            with tempfile.TemporaryDirectory(prefix='evidence-acl-') as temp:
                saved=Path(temp)/'acl.txt'
                saved.write_bytes(bytes.fromhex(e['original_acl_hex']))
                checked('icacls', str(p.parent), '/restore', str(saved))
        if 'attrib +R' in e['applied']: checked('attrib', '-R', str(p))
        if 'chmod a-w' in e['applied'] and stat.S_IMODE(p.lstat().st_mode) != e['mode']: p.chmod(e['mode'])


def verify(record):
    if record.get('platform') != sys.platform:
        return []  # Caller reports protection unverified; hashes remain authoritative.
    problems = []
    for e in record.get('entries', []):
        p = Path(e['path'])
        try:
            s = p.lstat()
            if p.is_symlink() or not same_identity(s, e):
                problems.append(f'PROTECTION identity changed: {p}')
            if e.get('status') == 'protected-by-media' and not read_only_media(p):
                problems.append(f'PROTECTION read-only media missing: {p}')
            if 'chmod a-w' in e['applied'] and os.name != 'nt' and s.st_mode & 0o222: problems.append(f'PROTECTION writable: {p}')
            if 'uchg' in e['applied'] and not s.st_flags & stat.UF_IMMUTABLE:
                problems.append(f'PROTECTION uchg missing: {p}')
            if 'chattr +i' in e['applied'] and 'i' not in checked('lsattr', '-d', str(p)).split()[0]:
                problems.append(f'PROTECTION immutable missing: {p}')
            if ('attrib +R' in e['applied'] or 'deny-write ACL' in e['applied']) and not s.st_file_attributes & stat.FILE_ATTRIBUTE_READONLY:
                problems.append(f'PROTECTION read-only attribute missing: {p}')
            if 'deny-write ACL' in e['applied'] and not acl_present(e):
                problems.append(f'PROTECTION deny-write ACL missing: {p}')
        except OSError as exc:
            problems.append(f'PROTECTION unavailable: {p}: {exc}')
    return problems


if __name__ == '__main__':
    try:
        request = json.load(sys.stdin)
        action = request['action']
        if action == 'protect':
            result = protect(request['paths'], request.get('journal'))
        elif action == 'lock':
            result = lock(request['record'], request.get('journal'))
        elif action == 'verify':
            result = verify(request['record'])
        elif action == 'unlock':
            result = unlock(recovery_record(request['journal']) if not request.get('record') and request.get('journal') else request['record'])
        else:
            raise ValueError('Unknown protection action')
        json.dump(result, sys.stdout)
        print()
    except (OSError, ValueError, KeyError) as exc:
        print(f'OS protection: {exc}', file=sys.stderr)
        sys.exit(2)
