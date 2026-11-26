import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const guard = path.join(root, 'scripts/evidence_guard.mjs');

function decide(workspace, name, args) {
 const r = spawnSync(process.execPath, [guard, 'pre-tool-use'], {
  input: JSON.stringify({workspacePaths: [workspace], toolCall: {name, args}}), encoding: 'utf8', timeout: 30000,
 });
 const verdict = JSON.parse(r.stdout.trim().split('\n').at(-1));
 assert.equal(r.status, verdict.decision === 'deny' ? 1 : 0, r.stderr);
 return verdict.decision;
}
const write = (ws, target) => decide(ws, 'write_file', {TargetFile: target});
const command = (ws, line) => decide(ws, 'run_command', {CommandLine: line});

function withCase(parents, fn) {
 const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'neon-scope-'));
 try {
  const ws = path.join(tmp, ...parents, 'case1');
  fs.mkdirSync(path.join(ws, 'evidence'), {recursive: true});
  fs.writeFileSync(path.join(ws, 'evidence', 'a.txt'), 'synthetic evidence');
  fs.mkdirSync(path.join(ws, 'originals'));
  fs.writeFileSync(path.join(ws, 'originals', 'b.txt'), 'synthetic registered evidence');
  fs.writeFileSync(path.join(ws, 'manifest.json'), JSON.stringify({manifest_version: 1, root: 'originals', files: [{path: 'b.txt'}]}));
  fn(ws, tmp);
 } finally { fs.rmSync(tmp, {recursive: true, force: true}); }
}

// The review reproduced a deny for every write once an ancestor folder was named Evidence.
const LAYOUTS = [['cases'], ['Evidence'], ['a b', 'EVIDENCE']];

for (const parents of LAYOUTS) {
 const label = parents.join('/');
 test(`ordinary case writes are allowed under ${label}/case1`, () => withCase(parents, ws => {
  assert.equal(write(ws, 'report.md'), 'allow');
  assert.equal(write(ws, path.join(ws, 'report.md')), 'allow');
  assert.equal(write(ws, path.join(ws, 'reports', 'timeline.html')), 'allow');
  assert.equal(command(ws, `echo done > "${path.join(ws, 'out.txt')}"`), 'allow');
  assert.equal(command(ws, 'ffmpeg -i evidence/a.txt out.wav'), 'allow');
  assert.equal(command(ws, `sha256sum "${path.join(ws, 'evidence', 'a.txt')}"`), 'allow');
 }));

 test(`evidence protections still deny under ${label}/case1`, () => withCase(parents, (ws, tmp) => {
  assert.equal(write(ws, 'evidence/a.txt'), 'deny');
  assert.equal(write(ws, path.join(ws, 'evidence', 'new.txt')), 'deny');
  assert.equal(write(ws, path.join(ws, 'disk.E01')), 'deny');
  // case-mode / manifest identity protects folders not named evidence.
  assert.equal(write(ws, path.join(ws, 'originals', 'b.txt')), 'deny');
  assert.equal(command(ws, 'cp report.md evidence/'), 'deny');
  assert.equal(command(ws, `echo x > "${path.join(ws, 'evidence', 'a.txt')}"`), 'deny');
  assert.equal(command(ws, 'rm evid*/*.txt'), 'deny');
  assert.equal(command(ws, `python3 -c "import os; os.remove('evid'+'ence/a.txt')"`), 'deny');
  assert.equal(command(ws, 'ffmpeg -i in.wav -y evidence/a.mp4 out.wav'), 'deny');
  assert.equal(command(ws, 'powershell -enc AAAA'), 'deny');
  // Paths outside the workspace keep the full absolute-path check.
  fs.mkdirSync(path.join(tmp, 'other', 'evidence'), {recursive: true});
  assert.equal(write(ws, path.join(tmp, 'other', 'evidence', 'x.txt')), 'deny');
 }));
}

test('a workspace that is itself named evidence stays protected', () => {
 const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'neon-scope-'));
 try {
  const ws = path.join(tmp, 'evidence');
  fs.mkdirSync(ws);
  assert.equal(write(ws, 'report.md'), 'deny');
  assert.equal(write(ws, path.join(ws, 'report.md')), 'deny');
 } finally { fs.rmSync(tmp, {recursive: true, force: true}); }
});

test('writes into an Evidence ancestor outside the case stay denied', () => withCase(['Evidence'], ws => {
 assert.equal(write(ws, '../sibling.md'), 'deny');
 assert.equal(write(ws, path.join(path.dirname(ws), 'sibling.md')), 'deny');
}));

