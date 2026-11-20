// Domain summary with an optional read-only upstream notice.
import fs from 'node:fs';
import {companionLine, companionStatus} from './companion.mjs';
import {checkUpdate} from './update_notice.mjs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readHookStdin } from './hook_workspace.mjs';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
let payload = {};
try { payload = JSON.parse(await readHookStdin() || '{}'); } catch {}
const lines = [
  fs.readFileSync(path.join(root, 'rules/GEMINI.md'), 'utf8'),
  '\n## 런타임\n',
  'LazyNeon Workspace 0.2.1 — Antigravity / Gemini 4 Neon',
  `세션 모델: ${payload.modelName || '미확인 (호스트 보고값 없음)'}`,
  '모델 라우팅 및 일반 가드는 LazyNeon core가 관리한다.',
  '도메인 가드: evidence_guard, hallucination_guard, legal_factuality_guard, slop_guard.',
  '증거 원본 쓰기 금지. 근거 없는 수치·해시·시각·법령은 미확인. PII 최소화.',
  '외부 음성 전송은 명시적 --upload-audio 동의 필요.',
  '외부 MCP·호스트 훅의 실연동 상태는 미확인.',
];
lines.push(companionLine(companionStatus(root)));
const notice = checkUpdate({root});
if (notice) lines.push(notice);
process.stdout.write(JSON.stringify({injectSteps: [{systemMessage: {systemMessage: lines.join('\n')}}]}) + '\n', () => process.exit(0));
