"""Protection records keep exact file identities across the Node case-mode round trip."""
import json
import subprocess
import sys
from types import SimpleNamespace

from test_r6_workspace import ROOT

sys.path.insert(0, str(ROOT/'scripts'))
from evidence_protection import identity, same_identity  # noqa: E402

# NTFS file IDs carry a sequence number in the high bits, so they routinely exceed 2**53.
NTFS_LIKE = SimpleNamespace(st_dev=2894169731, st_ino=(37 << 48) | 123457)


def node_roundtrip(value):
    """What case_mode.mjs does with the record: JSON.parse, then JSON.stringify."""
    out = subprocess.run(['node', '-e', 'process.stdout.write(JSON.stringify(JSON.parse(require("fs").readFileSync(0,"utf8"))))'],
                         input=json.dumps(value), capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_numeric_identity_is_rounded_by_node():
    dev, ino = NTFS_LIKE.st_dev, NTFS_LIKE.st_ino
    assert node_roundtrip({'dev': dev, 'ino': ino})['ino'] != ino


def test_string_identity_survives_node_and_matches():
    dev, ino = identity(NTFS_LIKE)
    entry = node_roundtrip({'dev': dev, 'ino': ino})
    assert same_identity(NTFS_LIKE, entry)
    assert not same_identity(SimpleNamespace(st_dev=NTFS_LIKE.st_dev, st_ino=NTFS_LIKE.st_ino + 1), entry)


def test_records_written_before_the_change_still_match():
    assert same_identity(SimpleNamespace(st_dev=16777232, st_ino=1234567), {'dev': 16777232, 'ino': 1234567})


def test_verify_accepts_a_record_that_went_through_node(tmp_path):
    f = tmp_path/'sample.bin'; f.write_bytes(b'synthetic')
    dev, ino = identity(f.lstat())
    record = node_roundtrip({'platform': sys.platform, 'entries': [{'path': str(f), 'dev': dev, 'ino': ino, 'mode': 0o644, 'applied': []}], 'notes': []})
    r = subprocess.run([sys.executable, str(ROOT/'scripts/evidence_protection.py')], input=json.dumps({'action': 'verify', 'record': record}),
                       capture_output=True, text=True, cwd=str(ROOT/'scripts'))
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == []
