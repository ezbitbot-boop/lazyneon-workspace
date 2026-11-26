import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const GUARDS = ['evidence_guard.mjs', 'hallucination_guard.mjs', 'legal_factuality_guard.mjs', 'slop_guard.mjs'];

test('domain guards read stdin through the one shared reader', () => {
 for (const guard of GUARDS) {
  const source = fs.readFileSync(path.join(root, 'scripts', guard), 'utf8');
  assert.doesNotMatch(source, /function readStdin\b/, guard);
  assert.match(source, /import \{[^}]*\breadGuardStdin\b[^}]*\} from '\.\/hook_workspace\.mjs'/, guard);
 }
});

test('a payload that arrives in slow pieces is still judged as a whole', async () => {
 const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'neon-stdin-'));
 try {
  const payload = JSON.stringify({workspacePaths: [ws], toolCall: {name: 'write_file', args: {TargetFile: 'evidence/a.txt'}}});
  const child = spawn(process.execPath, [path.join(root, 'scripts/evidence_guard.mjs'), 'pre-tool-use']);
  let stdout = '';
  child.stdout.on('data', chunk => { stdout += chunk; });
  child.stdin.write(payload.slice(0, 40));
  await new Promise(resolve => setTimeout(resolve, 300));
  // The pipe stays open: the complete document alone must end the read.
  child.stdin.write(payload.slice(40));
  const status = await new Promise(resolve => child.on('close', resolve));
  child.stdin.destroy();
  assert.equal(status, 1);
  assert.equal(JSON.parse(stdout.trim()).decision, 'deny');
 } finally { fs.rmSync(ws, {recursive: true, force: true}); }
});
