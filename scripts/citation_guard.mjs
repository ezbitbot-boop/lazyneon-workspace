#!/usr/bin/env node
/**
 * citation_guard.mjs — 보고서가 인용한 값(해시·일시·인용문·파일명·단위 수치·인명·도구)이 증거 파일에서 나왔는지 대조한다.
 * 보고서 품질 검사다. 기본은 경고(WARN)만 하고 쓰기를 막지 않는다.
 * LAZYNEON_WS_CITATION_STRICT=1이면 근거 없는 값이 있거나 검사하지 못했을 때 FAIL/NOT_CHECKED로 차단한다.
 * 보고서·증거 폴더 판정은 hallucination_guard와 같은 report_scope.mjs를 쓴다.
 *   PostToolUse: stdin 페이로드 → stderr "[CITATION GUARD] WARN …", stdout {status}, exit 0 (strict 차단만 exit 1)
 *   CLI:         python scripts/citation_grounding.py <보고서> --evidence <폴더|파일...>
 */
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { contentTargets, isCoreOwned } from './hook_targets.mjs';
import { resolveWorkspace, readGuardStdin } from './hook_workspace.mjs';
import { pythonCandidates, isPythonLauncherStub } from './python_runtime.mjs';
import { REPORT_EXT_RE, shouldGuard, sourceCandidates, evidenceCandidates, isMessengerExport } from './report_scope.mjs';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const script = path.join(root, 'scripts', 'citation_grounding.py');
const strict = process.env.LAZYNEON_WS_CITATION_STRICT === '1';
// domain_feedback gives each guard run at most 30 s.
const TIMEOUT_MS = 25000;
const SHOWN = 12;

function runChecker(target, evidence) {
	for (const { cmd, pre } of pythonCandidates(root)) {
		const res = spawnSync(cmd, [...pre, script, target, '--evidence', ...evidence, '--json'], { cwd: root, encoding: 'utf-8', windowsHide: true, timeout: TIMEOUT_MS, maxBuffer: 16 * 1024 * 1024 });
		if (res.error?.code === 'ENOENT' || isPythonLauncherStub(res)) continue;
		if (res.error) return { code: res.error.code === 'ETIMEDOUT' ? 'TIMEOUT' : 'CRASH' };
		try { return { result: JSON.parse(res.stdout) }; } catch { return { code: 'CRASH' }; }
	}
	return { code: 'PYTHON_UNAVAILABLE' };
}

function warning(file, result) {
	const unsupported = result.items.filter((i) => i.status === 'unsupported');
	const kinds = Object.entries(result.unsupported_by_kind).map(([k, n]) => `${k} ${n}`).join(', ');
	return [
		`[CITATION GUARD] WARN — ${path.basename(file)}: 증거에서 찾지 못한 인용 값 ${unsupported.length}건 (${kinds}) / 인용 ${result.cited}건`,
		...unsupported.slice(0, SHOWN).map((i) => `- L${i.line} ${i.kind}: ${i.value.slice(0, 80)}`),
		...(unsupported.length > SHOWN ? [`- … 외 ${unsupported.length - SHOWN}건`] : []),
		'증거에 있는 값으로 고치거나, 직접 계산한 값이면 그 줄에 계산 근거를 적고, 확인하지 못한 값은 [미확인]으로 표시하라.',
		`[CMD] python scripts/citation_grounding.py "${file}" --evidence <증거 폴더>`,
	].join('\n') + '\n';
}

async function hook() {
	const raw = await readGuardStdin();
	let payload = {};
	try { payload = JSON.parse(raw || '{}'); } catch {}
	const workspace = resolveWorkspace(payload);
	let checked = false, warned = false, unchecked = null;
	for (const file of contentTargets([{ parsed: payload }]).filter((t) => !isCoreOwned(t))) {
		if (!REPORT_EXT_RE.test(file) || !fs.existsSync(file) || isMessengerExport(file)) continue;
		// Generator artifacts (case_survey, court_evidence_sheet …) are tool output, not model prose.
		if (fs.readFileSync(file, 'utf8').startsWith('<!-- lazyneon-artifact:')) continue;
		if (!shouldGuard(file, [raw], workspace)) continue;
		const evidence = [...new Set([...sourceCandidates(file, workspace), ...evidenceCandidates(file, workspace)])];
		if (!evidence.length) continue;
		const { result, code } = runChecker(file, evidence);
		if (!result) {
			unchecked = code;
			console.error(`[CITATION GUARD] [미확인] ${path.basename(file)}: 인용 대조 미완료 (${code})`);
			continue;
		}
		checked = true;
		if (result.unsupported > 0) {
			warned = true;
			process.stderr.write(warning(file, result));
		}
	}
	if (warned && strict) {
		console.log(JSON.stringify({ status: 'FAIL', decision: 'block', reason: '[CITATION GUARD] 증거에서 찾지 못한 인용 값 (LAZYNEON_WS_CITATION_STRICT=1)' }));
		process.exit(1);
	}
	if (unchecked) {
		console.log(JSON.stringify({ status: 'NOT_CHECKED', code: unchecked, ...(strict ? { decision: 'block', reason: '[미확인] citation guard incomplete' } : {}) }));
		process.exit(strict ? 1 : 0);
	}
	console.log(JSON.stringify({ status: warned ? 'WARN' : checked ? 'PASS' : 'NOT_APPLICABLE' }));
	process.exit(0);
}

hook().catch(() => {
	console.error('[CITATION GUARD] [미확인] 검사 중 오류');
	console.log(JSON.stringify({ status: 'NOT_CHECKED', code: 'CRASH', ...(strict ? { decision: 'block', reason: '[미확인] citation guard crash' } : {}) }));
	process.exit(strict ? 1 : 0);
});
