import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const readme = fs.readFileSync(path.join(root, 'README.md'), 'utf8');
const block = lang => [...readme.matchAll(new RegExp('```' + lang + '\\n([\\s\\S]*?)```', 'g'))].map(m => m[1]).find(b => b.includes('pull --ff-only'));

function git(cwd, ...args) {
 const r = spawnSync('git', ['-c', 'user.name=synthetic', '-c', 'user.email=synthetic@example.invalid', '-c', 'commit.gpgsign=false', ...args], {cwd, encoding: 'utf8'});
 assert.equal(r.status, 0, r.stderr);
 return r.stdout.trim();
}
// origin is one commit ahead of the installed clone.
function withInstall(fn) {
 const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'neon-update-'));
 try {
  const origin = path.join(tmp, 'origin'), plugin = path.join(tmp, 'Plugins', 'lazyneon-workspace');
  fs.mkdirSync(origin);
  git(origin, 'init', '-q');
  fs.writeFileSync(path.join(origin, 'a.txt'), 'one\n');
  git(origin, 'add', 'a.txt'); git(origin, 'commit', '-q', '-m', 'one');
  git(tmp, 'clone', '-q', origin, plugin);
  fs.writeFileSync(path.join(origin, 'a.txt'), 'two\n');
  git(origin, 'commit', '-q', '-am', 'two');
  fn({plugin, upstream: git(origin, 'rev-parse', 'HEAD')});
 } finally { fs.rmSync(tmp, {recursive: true, force: true}); }
}

function check(t, run) {
 withInstall(({plugin, upstream}) => {
  fs.writeFileSync(path.join(plugin, 'local.txt'), 'untracked\n');
  const before = git(plugin, 'rev-parse', 'HEAD');
  const refused = run(plugin);
  if (refused.error?.code === 'ENOENT') return t.skip('shell not installed');
  assert.notEqual(refused.status, 0);
  assert.match(refused.stderr, /Refusing update: local changes/);
  assert.equal(git(plugin, 'rev-parse', 'HEAD'), before);
  fs.rmSync(path.join(plugin, 'local.txt'));
  const updated = run(plugin);
  assert.equal(updated.status, 0, updated.stderr);
  assert.equal(git(plugin, 'rev-parse', 'HEAD'), upstream);
 });
}

test('README Windows update command refuses local changes and fast-forwards', t => {
 const script = block('powershell');
 assert.ok(script, 'PowerShell update block');
 check(t, plugin => spawnSync('pwsh', ['-NoProfile', '-NonInteractive', '-Command', script.replace(/^\$p = .*$/m, `$p = '${plugin.replaceAll("'", "''")}'`)], {encoding: 'utf8'}));
});

test('README macOS update command refuses local changes and fast-forwards', t => {
 if (process.platform === 'win32') return t.skip('POSIX sh command');
 const script = block('sh');
 assert.ok(script, 'sh update block');
 check(t, plugin => spawnSync('sh', ['-c', script.replace(/^p="[^"]*"/, `p='${plugin}'`)], {encoding: 'utf8'}));
});
