import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const relay = path.join(root, 'scripts/domain_feedback.mjs');
const id = conversation => crypto.createHash('sha256').update(conversation).digest('hex');
const line = (n, kind = 'fail') => JSON.stringify({timestamp: '2026-11-26T00:00:00.000Z', workspace: '/synthetic/case', guard: 'slop_guard.mjs', target: `/synthetic/case/report-${n}.md`, kind, message: `verdict ${n}`}) + '\n';

function withHome(fn) {
 const home = fs.mkdtempSync(path.join(os.tmpdir(), 'neon-feedback-'));
 try { fn(home, path.join(home, '.lazyneon-workspace', 'feedback')); } finally { fs.rmSync(home, {recursive: true, force: true}); }
}
function inject(home, conversationId) {
 // os.homedir() reads USERPROFILE on Windows and HOME elsewhere.
 const r = spawnSync(process.execPath, [relay, 'inject'], {input: JSON.stringify({conversationId}), encoding: 'utf8', env: {...process.env, HOME: home, USERPROFILE: home}});
 assert.equal(r.status, 0, r.stderr);
 return JSON.parse(r.stdout);
}

test('inject delivers pending verdicts once and deletes them', () => withHome((home, dir) => {
 fs.mkdirSync(dir, {recursive: true});
 fs.writeFileSync(path.join(dir, `${id('case-a')}.jsonl`), line(1) + line(2, 'pass'));
 const out = inject(home, 'case-a');
 assert.match(out.injectSteps[0].ephemeralMessage, /verdict 1/);
 assert.doesNotMatch(out.injectSteps[0].ephemeralMessage, /verdict 2/);
 assert.deepEqual(fs.readdirSync(dir), []);
 assert.deepEqual(inject(home, 'case-a'), {});
}));

test('legacy cursor queues deliver only unseen lines, then both files are removed', () => withHome((home, dir) => {
 fs.mkdirSync(dir, {recursive: true});
 const queue = path.join(dir, `${id('legacy')}.jsonl`);
 fs.writeFileSync(queue, line(1) + line(2) + line(3));
 fs.writeFileSync(`${queue}.cursor`, '2');
 const message = inject(home, 'legacy').injectSteps[0].ephemeralMessage;
 assert.match(message, /verdict 3/);
 assert.doesNotMatch(message, /verdict [12]/);
 assert.deepEqual(fs.readdirSync(dir), []);
}));

test('queues nobody collected expire after a day', () => withHome((home, dir) => {
 fs.mkdirSync(dir, {recursive: true});
 const stale = [`${id('old')}.jsonl`, `${id('old')}.jsonl.cursor`, `${id('crashed')}.jsonl.4242.taking`];
 const fresh = `${id('current')}.jsonl`;
 const unrelated = 'notes.txt';
 for (const name of [...stale, fresh, unrelated]) fs.writeFileSync(path.join(dir, name), line(9));
 const twoDaysAgo = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000);
 for (const name of [...stale, unrelated]) fs.utimesSync(path.join(dir, name), twoDaysAgo, twoDaysAgo);
 assert.deepEqual(inject(home, 'someone-else'), {});
 assert.deepEqual(fs.readdirSync(dir).sort(), [fresh, unrelated].sort());
}));
