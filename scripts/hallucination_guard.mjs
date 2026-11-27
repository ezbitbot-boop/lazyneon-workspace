#!/usr/bin/env node
import {isCoreOwned, dispatchTargets} from './hook_targets.mjs';
import { shouldGuard, evidenceCandidates, sourceCandidates, isMessengerExport } from './report_scope.mjs';
import { pythonCandidates, isPythonLauncherStub } from './python_runtime.mjs';
import { workspaceFromSources, resolveTarget, readGuardStdin } from './hook_workspace.mjs';
let workspace = null;
/**
 * hallucination_guard.mjs — PostToolUse 호스트 강제 할루시네이션 가드
 * "보고서" / "검토해줘" 트리거가 포함된 모든 쓰기 후 무조건 실행을 목표로 한다.
 *
 * 정직한 동작 규약 (docs/GAPS.md 참고):
 * - 이 훅은 PostToolUse다. 파일이 이미 디스크에 쓰인 뒤 검증하므로 차단은 "사후 게이트"다 —
 *   호스트가 exit 1 을 받아 다음 턴에서 수정을 강제하는 방식이다. 이미 쓰인 파일을 지우지 않는다.
 * - 실제 차단은 호스트가 hooks.json 의 failurePolicy: FAIL_CLOSED 로 exit 1 을 해석할 때만 작동한다.
 * - Python 또는 검증 의존성이 없으면 미확인으로 차단한다.
 * - 스킵 경로: .md/.html/.txt 외 확장자, 호스트 미훅 경로, 키워드 없는 비보고서 쓰기.
 *
 * stdin 규약: 1.5초 데드라인 비동기 읽기 (Linux/Windows 파이프 호환 — fstat.size 미사용).
 */
import crypto from 'node:crypto';
import fs from 'fs';
import os from 'node:os';
import path from 'path';
import { spawnSync } from 'child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

// ---------------------------------------------------------------------------
// 입력 수집 (evidence_guard.mjs 와 동일 규약 — 소스별 독립 파싱)
// ---------------------------------------------------------------------------

function tryParseJson(text) {
	if (!text) return undefined;
	const t = text.trim();
	if (!t.startsWith('{') && !t.startsWith('[')) return undefined;
	try {
		return JSON.parse(t);
	} catch {
		return undefined;
	}
}

async function collectSources() {
	const sources = [];
	const push = (text, label) => {
		if (text) sources.push({ text, parsed: tryParseJson(text), label });
	};
	for (const k of ['ANTIGRAVITY_TOOL_INPUT', 'TOOL_INPUT', 'ANTIGRAVITY_TARGET_FILE', 'TARGET_FILE']) {
		if (process.env[k]) push(process.env[k], `env:${k}`);
	}
	push(await readGuardStdin(), 'stdin');
	for (const arg of process.argv.slice(2)) push(arg, 'argv');
	return sources;
}

// ---------------------------------------------------------------------------
// 대상 추정: JSON 경로 키 > 리다이렉트/유니코드 경로 정규식 > argv 존재 검사
// ---------------------------------------------------------------------------

const WRITE_OR_CMD_TOOL_RE = /^(write_to_file|replace_file_content|multi_replace_file_content|run_command|WriteToFile|ReplaceFileContent|MultiReplaceFileContent|RunCommand|write_file|WriteFile|edit_file|EditFile|Write|Edit|MultiEdit|SearchReplace|StrReplace|Bash|bash|Shell|shell|execute_command)$/i;
const TARGET_KEY_RE = /^(file_path|filepath|path|target|target_file|targetfile|target_path|targetpath|output|file|filename)$/i;
// \S 기반 — 한글/공백 파일명도 매칭 (구버전 [\w\-\.] 은 ASCII 한정으로 한글 보고서를 놓쳤다)
const PATH_LIKE_RE = /([^\s"'`<>|;&]+[\/\\][^\s"'`<>|;&]+\.(?:md|html|txt|json))/i;
const REDIRECT_RE = /(?:>|>>)\s*([^\s|&;]+(?:\.(?:md|html|txt|json)))/i;
const ARGV_REPORT_RE = /\.(md|html|txt)$/;

function unquoteTranscriptVal(val) {
	if (typeof val !== 'string') return val;
	const t = val.trim();
	if (t.length >= 2 && t.startsWith('"') && t.endsWith('"')) {
		try {
			const parsed = JSON.parse(t);
			if (typeof parsed === 'string') return parsed;
		} catch {
			return t.slice(1, -1);
		}
	}
	return val;
}

function resolveTranscriptPaths(payloadOrPath) {
	if (typeof payloadOrPath === 'string') {
		return resolveTranscriptPaths({ transcriptPath: payloadOrPath });
	}
	if (!payloadOrPath || typeof payloadOrPath !== 'object') return [];
	const candidates = [];
	const add = (p) => {
		if (typeof p === 'string' && p.trim() && !candidates.includes(p.trim())) {
			candidates.push(p.trim());
		}
	};
	const tp = payloadOrPath.transcriptPath || payloadOrPath.transcript_path || '';
	if (typeof tp === 'string' && tp.trim()) {
		add(tp);
		if (/transcript\.jsonl$/i.test(tp) && !/transcript_full\.jsonl$/i.test(tp)) {
			add(tp.replace(/transcript\.jsonl$/i, 'transcript_full.jsonl'));
		} else if (/transcript_full\.jsonl$/i.test(tp)) {
			add(tp.replace(/transcript_full\.jsonl$/i, 'transcript.jsonl'));
		}
	}
	const adp = payloadOrPath.artifactDirectoryPath || payloadOrPath.artifact_directory_path || '';
	if (typeof adp === 'string' && adp.trim()) {
		add(path.join(adp, '.system_generated', 'logs', 'transcript_full.jsonl'));
		add(path.join(adp, '.system_generated', 'logs', 'transcript.jsonl'));
		add(path.join(adp, 'transcript_full.jsonl'));
		add(path.join(adp, 'transcript.jsonl'));
	}
	return candidates.filter((p) => {
		try {
			return fs.existsSync(p) && fs.statSync(p).isFile();
		} catch {
			return false;
		}
	});
}

function extractToolDataFromCall(tc) {
	if (!tc || typeof tc !== 'object') return null;
	const toolName = unquoteTranscriptVal(tc.name || tc.tool_name || tc.toolName || tc.function?.name || '');
	if (toolName && !WRITE_OR_CMD_TOOL_RE.test(toolName)) return null;
	let rawArgs = tc.args ?? tc.arguments ?? tc.input ?? tc.parameters ?? tc.function?.arguments ?? tc;
	if (typeof rawArgs === 'string') {
		rawArgs = tryParseJson(unquoteTranscriptVal(rawArgs)) ?? tryParseJson(rawArgs);
	}
	if (!rawArgs || typeof rawArgs !== 'object') return null;

	const getStr = (...keys) => {
		for (const k of keys) {
			if (typeof rawArgs[k] === 'string' && rawArgs[k]) {
				return unquoteTranscriptVal(rawArgs[k]);
			}
		}
		return '';
	};

	let targetFile = getStr('TargetFile', 'target_file', 'file_path', 'filepath', 'Path', 'path', 'target', 'target_path', 'targetpath', 'output', 'file', 'filename');
	const commandLine = getStr('CommandLine', 'command_line', 'command', 'cmd', 'script');
	let codeContent = getStr('CodeContent', 'code_content', 'ReplacementContent', 'replacement_content', 'Content', 'content', 'Replacement', 'replacement', 'new_string', 'text');
	if (!codeContent && rawArgs.ReplacementChunks !== undefined) {
		let chunks = rawArgs.ReplacementChunks;
		if (typeof chunks === 'string') {
			chunks = tryParseJson(unquoteTranscriptVal(chunks)) ?? tryParseJson(chunks);
		}
		if (Array.isArray(chunks)) {
			codeContent = chunks
				.map((c) => (c && typeof c === 'object' ? unquoteTranscriptVal(c.ReplacementContent || c.replacement_content || c.content || '') : ''))
				.filter(Boolean)
				.join('\n');
		}
	}
	if (!targetFile && commandLine) {
		const red = commandLine.match(REDIRECT_RE);
		if (red) targetFile = red[1];
		else {
			const m = commandLine.match(PATH_LIKE_RE);
			if (m) targetFile = m[1];
		}
	}
	if (!targetFile && !commandLine && !codeContent) return null;
	return { toolName, targetFile, codeContent, commandLine };
}

function extractTargetFromNode(node, out) {
	if (Array.isArray(node)) {
		for (const item of node) extractTargetFromNode(item, out);
		return;
	}
	if (!node || typeof node !== 'object') return;
	for (const [key, value] of Object.entries(node)) {
		if (typeof value === 'string' && value) {
			if (key === 'Target' && ('Path' in node || 'Replacement' in node)) continue;
			if (TARGET_KEY_RE.test(key)) out.push({ value, isCommand: false });
			else if (/^(command|cmd|command_line|commandline|script|args)$/i.test(key)) out.push({ value, isCommand: true }); // bash 리다이렉트 대상
		} else if (value && typeof value === 'object') {
			extractTargetFromNode(value, out);
		}
	}
}

// 마지막 줄이 32KB 창보다 길면(큰 쓰기 직후) 창 안에 완결된 줄이 없어 0줄이 된다.
// 그때만 예전 상한(512KB)으로 한 번 더 읽는다.
const TAIL_FALLBACK_BYTES = 512 * 1024;

function readTailLines(filePath, maxLines = 5, maxBytes = 32 * 1024) {
	const stat = fs.statSync(filePath);
	let text;
	if (stat.size <= maxBytes) {
		text = fs.readFileSync(filePath, 'utf8');
	} else {
		const fd = fs.openSync(filePath, 'r');
		let complete = true;
		try {
			const buf = Buffer.allocUnsafe(maxBytes);
			fs.readSync(fd, buf, 0, maxBytes, stat.size - maxBytes);
			const nlIdx = buf.indexOf(0x0a);
			complete = nlIdx >= 0 && nlIdx < maxBytes - 1;
			text = (nlIdx >= 0 ? buf.subarray(nlIdx + 1) : buf).toString('utf8');
		} finally {
			fs.closeSync(fd);
		}
		if (!complete && maxBytes < TAIL_FALLBACK_BYTES) return readTailLines(filePath, maxLines, TAIL_FALLBACK_BYTES);
	}
	return text.split(/\r?\n/).filter((l) => l.trim().length > 0).slice(-maxLines).reverse();
}

function extractFromTranscript(payloadOrPath) {
	const paths = resolveTranscriptPaths(payloadOrPath);
	const targetStepIdx =
		payloadOrPath && typeof payloadOrPath === 'object'
			? typeof payloadOrPath.stepIdx === 'number'
				? payloadOrPath.stepIdx
				: typeof payloadOrPath.step_index === 'number'
					? payloadOrPath.step_index
					: undefined
			: undefined;

	for (const tp of paths) {
		try {
			const lines = readTailLines(tp, 5);
			const parsedSteps = [];
			let hasTruncatedToolCalls = false;
			for (const line of lines) {
				const step = tryParseJson(line);
				if (!step || typeof step !== 'object') continue;
				if (Array.isArray(step.truncated_fields) && step.truncated_fields.includes('tool_calls')) {
					hasTruncatedToolCalls = true;
				}
				parsedSteps.push({ step, line });
			}
			if (hasTruncatedToolCalls && paths.some((p) => p !== tp && /transcript_full\.jsonl$/i.test(p))) {
				continue;
			}

			let matchedToolStep = false;
			const searchSteps = (respectStepIdx) => {
				for (const { step, line } of parsedSteps) {
					const stepIdxVal = typeof step.step_index === 'number' ? step.step_index : typeof step.stepIdx === 'number' ? step.stepIdx : undefined;
					if (respectStepIdx && targetStepIdx !== undefined && stepIdxVal !== undefined && stepIdxVal > targetStepIdx) {
						continue;
					}
					const calls = Array.isArray(step.tool_calls)
						? step.tool_calls
						: Array.isArray(step.toolCalls)
							? step.toolCalls
							: step.toolCall && typeof step.toolCall === 'object'
								? [step.toolCall]
								: [];
					if (calls.length > 0) {
						if (respectStepIdx) matchedToolStep = true;
						if (respectStepIdx && targetStepIdx !== undefined && stepIdxVal !== undefined && targetStepIdx > stepIdxVal) {
							const callOffset = targetStepIdx - stepIdxVal - 1;
							if (callOffset >= 0 && callOffset < calls.length) {
								const data = extractToolDataFromCall(calls[callOffset]);
								return data && data.targetFile ? data : null;
							}
						}
						for (let i = calls.length - 1; i >= 0; i -= 1) {
							const data = extractToolDataFromCall(calls[i]);
							if (data && data.targetFile) return data;
						}
						return null;
					}
					const directData = extractToolDataFromCall(step);
					if (directData && directData.targetFile) return directData;
					if (WRITE_OR_CMD_TOOL_RE.test(line)) {
						const found = [];
						extractTargetFromNode(step, found);
						for (const { value, isCommand } of found) {
							const u = unquoteTranscriptVal(value);
							if (!isCommand && u) return { toolName: '', targetFile: u, codeContent: '', commandLine: '' };
							if (isCommand && u) {
								const red = u.match(REDIRECT_RE);
								if (red) return { toolName: 'run_command', targetFile: red[1], codeContent: '', commandLine: u };
								const m = u.match(PATH_LIKE_RE);
								if (m) return { toolName: 'run_command', targetFile: m[1], codeContent: '', commandLine: u };
							}
						}
					}
				}
				return null;
			};

			const hit = searchSteps(true) || (!matchedToolStep && targetStepIdx !== undefined ? searchSteps(false) : null);
			if (hit) return hit;
		} catch {
			// continue to next candidate
		}
	}
	return null;
}

function extractTarget(sources) {
	const env = process.env.ANTIGRAVITY_TARGET_FILE || process.env.TARGET_FILE || '';
	if (env) return env;
	for (const s of sources) {
		if (s.parsed !== undefined) {
			if (s.parsed?.toolCall?.args?.TargetFile) return unquoteTranscriptVal(String(s.parsed.toolCall.args.TargetFile));
			const found = [];
			extractTargetFromNode(s.parsed, found);
			for (const { value, isCommand } of found) {
				const u = unquoteTranscriptVal(value);
				if (!isCommand) return u; // file_path/target/output 는 그대로 대상
				// command 값은 리다이렉트/경로 정규식으로 재추출
				const red = u.match(REDIRECT_RE);
				if (red) return red[1];
				const m = u.match(PATH_LIKE_RE);
				if (m) return m[1];
			}
			if (
				s.parsed &&
				typeof s.parsed === 'object' &&
				(s.parsed.transcriptPath || s.parsed.transcript_path || s.parsed.artifactDirectoryPath || s.parsed.artifact_directory_path)
			) {
				const fromTranscript = extractFromTranscript(s.parsed);
				if (fromTranscript && fromTranscript.targetFile) return fromTranscript.targetFile;
			}
		}
	}
	for (const s of sources) {
		if (s.parsed !== undefined) continue;
		const red = s.text.match(REDIRECT_RE);
		if (red) return red[1];
		const m = s.text.match(PATH_LIKE_RE);
		if (m) return m[1];
	}
	for (const arg of process.argv.slice(2)) {
		if (ARGV_REPORT_RE.test(arg) && fs.existsSync(arg)) return arg;
	}
	return '';
}

function ledgerCandidate(targetFile) {
	const dir = path.dirname(path.resolve(targetFile));
	const candidates = [
		join(dir, 'claim-ledger.md'),
		join(dir, 'claim_ledger.md'),
		join(workspace || dir, 'claim-ledger.md'),
		join(workspace || dir, 'claim_ledger.md'),
	];
	return candidates.find((p) => fs.existsSync(p));
}

// timeline 자동 탐색: 보고서 옆/작업 디렉터리의 timeline json — 시각 grounding.
// 여러 개 있으면 보고서와 가장 가까운(같은 디렉터리) 것부터 전달한다.
function timelineCandidates(targetFile) {
	const dir = path.dirname(path.resolve(targetFile));
	const candidates = [
		join(dir, 'timeline.json'),
		join(dir, 'timeline_events.json'),
		join(dir, 'events.json'),
		join(workspace || dir, 'timeline.json'),
		join(workspace || dir, 'timeline_events.json'),
		join(workspace || dir, 'events.json'),
	];
	return candidates.find((p) => fs.existsSync(p));
}

// Python 탐색: OS별 최적 순서 및 Windows Store alias 오탐 배제
const PYTHON_CANDIDATES = pythonCandidates(root);

// 호스트 훅 타임아웃(hooks.json 30초)보다 짧게 잡아, 검증이 길어져도 호스트가 프로세스를 죽여
// stdout JSON 없이 끝나는 상황을 막는다. 타임아웃은 "검증 미완료"이며 FAIL_CLOSED(exit 1)다 —
// 호스트 세션의 긴 보고서 + Kiwi 형태소 그라운딩이 30초를 넘는 사례 대응.
const VERIFY_TIMEOUT_MS = Number.parseInt(process.env.LAZYNEON_WS_VERIFY_TIMEOUT_MS || '', 10) || 25000;

function runVerify(args) {
	const attempts = [];
	for (const { cmd, pre } of PYTHON_CANDIDATES) {
		const res = spawnSync(cmd, [...pre, ...args], { cwd: root, encoding: 'utf-8', windowsHide: true, timeout: VERIFY_TIMEOUT_MS });
		if (res.error) {
			if (res.error.code === 'ENOENT') {
				attempts.push(`${cmd}: not found`);
				continue;
			}
			if (res.error.code === 'ETIMEDOUT') {
				return { res, cmd, spawnError: false, timedOut: true, attempts };
			}
			return { res, cmd, spawnError: true, attempts };
		}
		if (isPythonLauncherStub(res)) {
			// Windows Store app-execution alias — 진짜 인터프리터가 아니다
			attempts.push(`${cmd}: store alias`);
			continue;
		}
		return { res, cmd, spawnError: false, attempts };
	}
	return { res: null, cmd: null, spawnError: false, attempts };
}

function notChecked(detail) {
    const reason = `[미확인] NOT_CHECKED: ${detail} — 검증 완료로 제출할 수 없습니다.`;
    console.error(reason);
    console.log(JSON.stringify({decision: 'block', status: 'NOT_CHECKED', reason}));
    process.exit(1);
}

async function main() {
	const sources = await collectSources();
	workspace = workspaceFromSources(sources);
	dispatchTargets(sources);
	const rawTexts = sources.map((s) => s.text);
	let targetFile = resolveTarget(extractTarget(sources), workspace);
	if (targetFile && isCoreOwned(targetFile)) { console.log(JSON.stringify({status:'NOT_APPLICABLE'})); process.exit(0); }

	// Fast-path: if targetFile is already resolved and is not a report extension (.md/.html/.txt), exit immediately
	if (targetFile && !/\.(md|html|txt)$/i.test(targetFile)) {
		process.stdout.write(JSON.stringify({status:'NOT_APPLICABLE'})+'\n');
		process.exit(0);
	}

	for (const s of sources) {
		if (
			s.parsed &&
			typeof s.parsed === 'object' &&
			(s.parsed.transcriptPath || s.parsed.transcript_path || s.parsed.artifactDirectoryPath || s.parsed.artifact_directory_path)
		) {
			const fromTranscript = extractFromTranscript(s.parsed);
			if (fromTranscript) {
				if (!targetFile && fromTranscript.targetFile) targetFile = resolveTarget(fromTranscript.targetFile, workspace);
				if (fromTranscript.targetFile) rawTexts.push(fromTranscript.targetFile);
				if (fromTranscript.codeContent) rawTexts.push(fromTranscript.codeContent);
				if (fromTranscript.commandLine) rawTexts.push(fromTranscript.commandLine);
			}
		}
	}

	if (!targetFile || isCoreOwned(targetFile) || !/\.(md|html|txt)$/i.test(targetFile) || !fs.existsSync(targetFile)) {
		process.stdout.write(JSON.stringify({status:'NOT_APPLICABLE'})+'\n');
		process.exit(0); // 가드 대상 없음 — 오탐 방지
	}
	if (isMessengerExport(targetFile)) {
		process.stdout.write(JSON.stringify({status:'NOT_APPLICABLE'})+'\n');
		process.exit(0);
	}
    let artifactHashCheck=false;
    // Generators hash LF text; Windows text-mode writes and editors save CRLF.
    const artifact=fs.readFileSync(targetFile,'utf8').replace(/\r\n/g,'\n');
    if(artifact.startsWith('<!-- lazyneon-artifact:')) {
        const m=artifact.match(/^<!-- lazyneon-artifact:v1 kind=non-report generator=(case_survey|court_evidence_sheet|generate_evidence_doc) sha256=([a-f0-9]{64}) -->\n/);
        const valid=m&&crypto.createHash('sha256').update(artifact.slice(m[0].length),'utf8').digest('hex')===m[2];
        if(!valid) {
            console.log(JSON.stringify({status:'FAIL',decision:'block',reason:'Generated artifact body changed; regenerate or verify as a report'}));
            process.exit(1);
        }
        artifactHashCheck=/(?:[a-f0-9]{64}|(?:MD5|SHA-?1)\s*[:=]?\s*[a-f0-9]{32,40})/i.test(artifact.slice(m[0].length));
        if(!artifactHashCheck) {console.log(JSON.stringify({status:'NOT_APPLICABLE'}));process.exit(0);}
    }
	if (!artifactHashCheck && !shouldGuard(targetFile, rawTexts, workspace)) {
		process.stdout.write(JSON.stringify({status:'NOT_APPLICABLE'})+'\n');
		process.exit(0);
	}

	const verifyScript = join(root, 'scripts', 'verify_report.py');
	if (!fs.existsSync(verifyScript)) notChecked('verifier 스크립트 없음');

	const evidence = evidenceCandidates(targetFile, workspace);
	const ledger = ledgerCandidate(targetFile);
	const timeline = timelineCandidates(targetFile);
    const timelineNeeded = !artifactHashCheck && /\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}/.test(fs.readFileSync(targetFile,'utf8'));
	const args = [verifyScript, targetFile, "--json"];
	if (evidence.length > 0) {
		args.push('--evidence', ...evidence);
        if(!artifactHashCheck)args.push('--morph-grounding');
	}
    if(artifactHashCheck) args.push('--artifact-hashes-only');
	if (timeline) {
		args.push('--timeline', timeline);
	} else if (timelineNeeded) {
		// timeline 근거 파일을 못 찾으면 과거 시각 grounding이 스킵된다.
		// 조용한 사각지대 대신 사용자에게 노출해 수동 제공을 유도한다. 단, 대화·보고서마다 한 번만 알린다
		// (실세션 2026-11-01: 같은 안내가 저장할 때마다 9번 반복돼 에이전트가 가드 코드를 뒤졌다).
		const noteKey = crypto.createHash('sha1').update(`${sources.find((s) => s.parsed && s.parsed.conversationId)?.parsed.conversationId || ''}|${path.resolve(targetFile)}`).digest('hex').slice(0, 16);
		const noteMark = workspace ? path.join(workspace, '.lazyneon-workspace', `timeline-note-${noteKey}`) : null;
		if (!noteMark || !fs.existsSync(noteMark)) {
			try {
				if (noteMark) {
					fs.mkdirSync(path.dirname(noteMark), { recursive: true });
					fs.writeFileSync(noteMark, '');
				}
			} catch {
				// 표시 기록 실패는 안내 자체를 막지 않는다
			}
			console.error(`[HALLUCINATION GUARD] timeline 근거 파일 미발견 — 타임라인 grounding 생략. timeline.json이 있다면 보고서와 같은 디렉터리에 두십시오: ${path.dirname(path.resolve(targetFile))}`);
		}
	}
	if (ledger) {
		args.push('--claim-ledger', ledger);
	}
	args.push('--require-sources', '--sources', ...sourceCandidates(targetFile, workspace));

	const { res, spawnError, timedOut, attempts } = runVerify(args);

	if (timedOut) {
		console.error(`[HALLUCINATION GUARD] 검증 미완료 — verify_report.py 가 ${VERIFY_TIMEOUT_MS}ms 안에 끝나지 않았다 (FAIL_CLOSED). "${path.basename(targetFile)}"`);
		console.error('[HINT] 보고서를 분할하거나 --morph-grounding 없이 수동 검증을 먼저 돌릴 것. 검증이 끝나기 전에는 제출하지 않는다.');
		console.error(`[CMD] python scripts/verify_report.py "${targetFile}" --evidence <manifest.json|receipt.json|audit_trail.jsonl> --json`);
		process.stdout.write(JSON.stringify({ decision: 'block', status: 'NOT_CHECKED', code: 'TIMEOUT', reason: `[HALLUCINATION GUARD] 검증 미완료(타임아웃) — ${path.basename(targetFile)}` }) + '\n');
		process.exit(1);
	}

	if (res === null) notChecked('python 실행 불가');
	if (spawnError) notChecked('verifier 실행 오류');

	let verified;
    try { verified=JSON.parse(res.stdout); } catch {}
	if (res.status !== 0) {
        if (!verified || !['FAIL','WARN','PASS'].includes(verified.verdict)) notChecked('verifier crash/dependency failure without verdict');
        if (verified?.status_codes?.includes('MORPH_UNAVAILABLE') && !verified.errors?.some(e=>!String(e).startsWith('[미확인]'))) {
            console.error('[HALLUCINATION GUARD] kiwipiepy 엔진 사용 불가');
            console.error((res.stderr||'')+(res.stdout||''));
            console.log(JSON.stringify({decision:'block',status:'NOT_CHECKED',code:'MORPH_UNAVAILABLE'}));
            process.exit(1);
        }
		const out = ((res.stderr || '') + '\n' + (res.stdout || '')).toString().trim();
		console.error(`[HALLUCINATION GUARD] 보고서 검증 FAIL — "${path.basename(targetFile)}" (PostToolUse 사후 게이트, 보고서/검토해줘 트리거)`);
		console.error(out.slice(0, 3500));
		console.error('[HINT] 금지문구 제거, 해시는 실파일 검증 매니페스트·성공 receipt·정상 audit chain 근거만 사용, 없으면 미확인/미측정으로 둘 것. 수정 후 재시도.');
		console.error(`[CMD] python scripts/verify_report.py "${targetFile}" --evidence <manifest.json|receipt.json|audit_trail.jsonl> --json`);
		process.stdout.write(JSON.stringify({ decision: 'block', status:'FAIL', reason: `[HALLUCINATION GUARD] 보고서 검증 FAIL — ${path.basename(targetFile)}` }) + '\n');
		process.exit(1);
	}

	if (!['PASS','WARN'].includes(verified?.verdict) && !/^\[(PASS|WARN)\]/m.test(res.stdout || '')) notChecked('verifier 결과 없음/잘못된 출력');

    if(artifactHashCheck) {console.log(JSON.stringify({status:'NOT_APPLICABLE'}));process.exit(0);}
	if (res.stdout && (verified?.verdict==='WARN' || res.stdout.includes('[WARN]'))) {
		console.error(`[HALLUCINATION GUARD] WARN — ${path.basename(targetFile)}: ${res.stdout.slice(0, 3500)}`);
	}
	process.stdout.write(JSON.stringify((!timeline && timelineNeeded)?{status:'NOT_CHECKED',code:'TIMELINE_UNAVAILABLE'}:(verified?.verdict==='WARN' || res.stdout.includes('[WARN]'))?{status:'WARN'}:{status:'PASS'})+'\n');
	process.exit(0);
}

main();
