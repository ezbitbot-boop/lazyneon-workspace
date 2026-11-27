/**
 * report_scope.mjs — which writes are reports and which folders ground them.
 * Shared by hallucination_guard (fail-closed verifier) and citation_guard (warn-level grounding)
 * so both guards judge the same files against the same evidence.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { isCoreOwned } from './hook_targets.mjs';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');

// 트리거는 키워드/경로힌트/본문 스니핑 3계층. 영어 일반 단어(summary,
// findings)는 본문 키워드에서 빼고 경로 힌트로만 쓴다 — 일반 개발 노트가
// 금지문구 스캐너까지 몰려 차단되는 과잉 트리거를 막는다.
const GUARD_KEYWORD_RE = /보고서|감정서|소견서|의견서|진단서|확인서|분석서|결과서|검토해줘|검증해줘|검증|할루시네이션|할루체크|팩트체크|거짓말검사|사실확인|무결성검사|verify|\/verify|\/할루체크|\/검증|법적.*검토|요약해줘|기록해줘|\/요약|\/기록/i;
const NON_REPORT_DOC_RE = /매뉴얼|가이드|튜토리얼|교재|핸드북|치트시트|강의|강좌|안내서|설명서|manual|guide|tutorial|handbook|cheatsheet|playbook|reference|readme/i;
const EXPLICIT_REPORT_NAME_RE = /보고서|감정서|소견서|의견서|진단서|확인서|분석서|결과서|타임라인|timeline|(?:^|[-_])(?:report|synthesis|findings|opinion)(?:[-_\.]|$)/i;
const READ_CAP_BYTES = 2 * 1024 * 1024; // shouldGuard 내용 훑기 상한
const TAIL_SAMPLE_BYTES = 512 * 1024; // 대용량 파일 후미 샘플 (후미 배치 우회 방지)
export const REPORT_EXT_RE = /\.(md|html|txt)$/i;

function readSamples(targetFile) {
	// 앞 2MB + 뒤 512KB 양단 샘플. 2MB 초과 파일은 뒤쪽 해시가 스니핑
	// 사각이 되는 것을 막는다. UTF-8 경계 절단은 라인 시작까지 되돌린다.
	const st = fs.statSync(targetFile);
	const headLen = Math.min(READ_CAP_BYTES, st.size);
	const fd = fs.openSync(targetFile, 'r');
	const head = Buffer.alloc(headLen);
	fs.readSync(fd, head, 0, headLen, 0);
	let tail = null;
	if (st.size > headLen) {
		const tailLen = Math.min(TAIL_SAMPLE_BYTES, st.size - headLen);
		tail = Buffer.alloc(tailLen);
		fs.readSync(fd, tail, 0, tailLen, st.size - tailLen);
		let start = 0;
		// tail 앞단이 잘린 멀티바이트면 첫 개행 이후부터 사용
		const nl = tail.indexOf(0x0a);
		if (nl > 0) start = nl + 1;
		tail = tail.subarray(start);
	}
	fs.closeSync(fd);
	return head.toString('utf-8') + (tail ? tail.toString('utf-8') : '');
}

function isPluginInternalDoc(targetFile) {
	try {
		const abs = path.resolve(targetFile);
		for (const pRoot of [path.resolve(root)]) {
			if (!abs.startsWith(pRoot + path.sep)) continue;
			const rel = path.relative(pRoot, abs).replace(/\\/g, '/');
			if (/^(AGENTS\.md|GEMINI\.md|RULES\.md|_entry\.md|README\.md|CLAUDE\.md|CHARTER\.md|NOTICE|rules\/|docs\/|skills\/|agents\/|templates\/|contracts\/|enforced\/)/.test(rel)) {
				return true;
			}
		}
		return false;
	} catch {
		return false;
	}
}

function isAgentInternalFile(targetFile, workspace) {
    if (isCoreOwned(targetFile)) return true;
    return Boolean(workspace && ['pins.md', 'ulw-scope.md', 'audit_trail.jsonl'].some(name => path.resolve(targetFile) === path.join(workspace, '.lazyneon-workspace', name)));
}

export function shouldGuard(targetFile, rawTexts, workspace) {
	if (isPluginInternalDoc(targetFile) || isAgentInternalFile(targetFile, workspace)) return false;
	// 원본 자료 폴더(evidence/증거/자료/원본/sources/첨부) 안의 비보고서 파일은 근거 원본이다. analysis/분석 폴더는 보고서를 두는 곳이라 제외하지 않는다.
	const RAW_SOURCE_DIRS = ['evidence', '증거', '자료', '원본', 'sources', 'attachments', '첨부', 'case'];
	if (RAW_SOURCE_DIRS.includes(path.basename(path.dirname(path.resolve(targetFile)))) && !EXPLICIT_REPORT_NAME_RE.test(path.basename(targetFile)) && !/보고서|초안|draft|report/i.test(path.basename(targetFile))) return false;
	const keywordHit = GUARD_KEYWORD_RE.test(rawTexts.join('\n'));
	const reportExt = REPORT_EXT_RE.test(targetFile);
	// 경로 힌트는 basename에만 적용 — 디렉터리명/부분문자열 오탐 방지.
	// 교육 매뉴얼/가이드(예: iOS_포렌식_판독_매뉴얼.md) 등 일반 참조 문서는
	// 대화나 본문에 '보고서'/'해시' 단어가 있더라도 사건 감정서가 아니므로 제외한다.
	const base = path.basename(targetFile);
	if (NON_REPORT_DOC_RE.test(base) && !EXPLICIT_REPORT_NAME_RE.test(base)) {
		return false;
	}
	const reportPathHint = /(?:^|[-_])(?:report|synthesis|summary|findings|notes|draft|analysis|opinion)(?:[-_\.]|$)/i.test(base)
		|| /보고서|감정서|소견서|의견서|진단서|확인서|분석서|결과서|초안|요약|기록/.test(base);
	if (keywordHit && reportExt) return true;
	if (reportExt && sourceCandidates(targetFile, workspace).length > 0) return true;
	if (reportPathHint && reportExt) return true;
	if (reportExt && fs.existsSync(targetFile)) {
		try {
			const text = readSamples(targetFile);
			// 본문 폴백: 포렌식 기술 패턴 조합 시 발동.
			// 1) SHA/MD5 라벨이 붙은 64hex 해시가 있으면서 포렌식 마커(감정/
			//    증거/사건/포렌식/타임스탬프)도 함께 있을 때만 발동 — 짧은
			//    "요약" 파일에 해시를 끼워 넣는 우회는 차단하고, 릴리스 체크섬
			//    노트(해시만 있음)는 발동하지 않는다.
			const hasLabeledHash = /(?:SHA-?256|sha256)\s*[:=]?\s*[a-fA-F0-9]{64}/i.test(text);
			const hasForensicMarker = /감정|증거|사건|포렌식|타임스탬프|timestamp/i.test(text);
			if (hasLabeledHash && hasForensicMarker) return true;
			if (text.length > 200) {
				const forensicMarkers = [
					/SHA-?256|MD5/i.test(text),
					/감정|증거|사건|포렌식|타임스탬프|timestamp/i.test(text),
				];
				if (forensicMarkers.filter(Boolean).length >= 2) return true;
				if (text.length > 500 && /(사건|감정|해시|SHA-256|증거)/.test(text)) return true;
			}
		} catch {}
	}
	return false;
}

// evidence 자동 탐색: 보고서 디렉터리·현재 작업 디렉터리 우선, 없을 때만(플러그인 내부 문서에 한해) 플러그인 루트 폴백
export function evidenceCandidates(targetFile, workspace) {
	const absTarget = path.resolve(targetFile);
	const dir = path.dirname(absTarget);
	const candidates = [path.join(dir, '.lazyneon-workspace', 'audit_trail.jsonl')];
	if (workspace) candidates.push(path.join(workspace, '.lazyneon-workspace', 'audit_trail.jsonl'));
    if (workspace) for (const folder of [workspace, path.join(workspace,'custody'), path.join(workspace,'.lazyneon-workspace')]) {
        let names=[];try {names=fs.readdirSync(folder);}catch{}
        for(const name of names.filter(n=>n.endsWith('.json'))) {
            const file=path.join(folder,name);
            try {
                const doc=JSON.parse(fs.readFileSync(file,'utf8'));
                if(doc.manifest_version===1 || doc.tool==='case_mode.mjs init' || doc.processing_receipt || (doc.source && doc.status && doc.artifacts)) candidates.push(file);
            } catch {}
        }
    }
	return [...new Set(candidates)].filter(p => fs.existsSync(p));
}

// 메신저 내보내기 원본(카카오톡 PC/모바일)은 보고서가 아니라 증거다. 실세션(2026-11-01): 원본 대화 파일을
// 보고서로 검사해 '김민수·금요일'을 증거에 없는 용어라고 경고했다.
export function isMessengerExport(targetFile) {
	if (!/\.txt$/i.test(targetFile)) return false;
	try {
		const head = fs.readFileSync(targetFile, 'utf8').slice(0, 2000);
		return /님과 카카오톡 대화|^\s*\[[^\]\n]{1,20}\]\s*\[(?:오전|오후)\s*\d{1,2}:\d{2}\]/m.test(head);
	} catch {
		return false; // 읽지 못하면 기존 판정을 따른다
	}
}

// 원본 자료 자동 탐색: 보고서 옆 자료 폴더(카톡·녹취·OCR 텍스트, 첨부 파일, 분석 산출물). 인용·첨부 대조 근거다.
// 'case': Windows QA(2026-11-02)에서 원본을 case\ 에 두었는데 자동 검증이 원본을 못 찾았다.
const SOURCE_DIR_NAMES = ['evidence', '증거', '자료', '원본', 'sources', 'materials', 'attachments', '첨부', 'analysis', '분석', 'case'];
export function sourceCandidates(targetFile, workspace) {
	const dir = path.dirname(path.resolve(targetFile));
    const result = [dir, workspace].filter(Boolean).flatMap(base=>SOURCE_DIR_NAMES.map(n=>path.join(base,n))).filter(p=>fs.existsSync(p)&&fs.statSync(p).isDirectory());
    for(const candidate of evidenceCandidates(targetFile, workspace)) {
        try {
            const doc=JSON.parse(fs.readFileSync(candidate,'utf8'));
            if(doc.manifest_version!==1 && doc.tool!=='case_mode.mjs init') continue;
            const base=path.resolve(path.dirname(candidate),doc.root||'.');
            for(const entry of doc.files||[]) {
                const file=path.resolve(base,entry.path);
                if(file!==path.resolve(targetFile) && fs.existsSync(file) && fs.statSync(file).isFile()) result.push(file);
            }
        } catch {}
    }
    return [...new Set(result)];
}
