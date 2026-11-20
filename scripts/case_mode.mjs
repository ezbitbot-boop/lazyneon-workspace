#!/usr/bin/env node
/**
 * case_mode.mjs — Case mode: sandbox-isolated evidence workspace for Antigravity / LazyNeon Workspace
 *
 * Usage:
 *   node scripts/case_mode.mjs init <evidence-path> [--out <case-work-dir>]
 *   node scripts/case_mode.mjs close [--case <case-work-dir>]
 *
 * Or via the bin wrapper:
 *   bin/case-mode init /path/to/evidence --out /path/to/case
 *   bin/case-mode close --case /path/to/case
 *
 * What 'init' does:
 *   1. Creates the case work directory (<evidence-parent>/case-<evidence-basename>-<local-date-offset> unless --out given).
 *   2. Writes <work>/.lazyneon-workspace/case-settings.json — Antigravity sandbox settings:
 *        enableTerminalSandbox, proceed-in-sandbox, evidence read_file only, deny write_file,
 *        deny download_url/execute_url, allow the research allowlist (other hosts fall back to Ask).
 *   3. Hashes every file in the evidence (SHA-256; E01 segments: each segment file).
 *      Writes <work>/custody/hashes-start.json and appends to <work>/custody/log.jsonl.
 *
 * What 'close' does:
 *   Re-hashes all evidence files recorded at init, fails loudly on any change, missing file,
 *   or unexpected new file. Appends a close event to custody/log.jsonl.
 */

import crypto from 'node:crypto';
import {workspaceProvenance} from './workspace_provenance.mjs';
const workspace_provenance = workspaceProvenance();
import {spawnSync} from 'node:child_process';
import {protection} from './evidence_protection.mjs';
import {canonical, within} from './evidence_identity.mjs';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// ---------------------------------------------------------------------------
// Research URL allowlist: config/case-mode-research-allowlist.json (owner-editable)
// ---------------------------------------------------------------------------
const ALLOWLIST_FILE = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'config', 'case-mode-research-allowlist.json');
const RESEARCH_URL_ALLOWLIST = JSON.parse(fs.readFileSync(ALLOWLIST_FILE, 'utf8')).hosts;

// ---------------------------------------------------------------------------
// SHA-256 streaming (avoids loading large evidence files into memory)
// ---------------------------------------------------------------------------
function sha256File(filePath) {
	return new Promise((resolve, reject) => {
		const hash = crypto.createHash('sha256');
		const stream = fs.createReadStream(filePath);
		stream.on('data', (chunk) => hash.update(chunk));
		stream.on('end', () => resolve(hash.digest('hex')));
		stream.on('error', reject);
	});
}

// ---------------------------------------------------------------------------
// Evidence discovery: folder → all files; E01 → segment set (E01, E02, …)
// ---------------------------------------------------------------------------
function collectEvidenceFiles(evidencePath, tolerateTypes = false) {
	const stat = fs.lstatSync(evidencePath);
	if (tolerateTypes && stat.isSymbolicLink()) return [evidencePath];
	if (stat.isSymbolicLink() && fs.statSync(evidencePath).isDirectory()) {
        throw new Error("Symlink evidence roots are unsupported; use the real directory");
    }
    if (stat.isSymbolicLink()) throw new Error('Symlink evidence roots are unsupported');
	if (stat.isDirectory()) {
		// Recursively collect all files under the directory
		const files = [];
		function walk(dir) {
			for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
				const full = path.join(dir, entry.name);
				if (entry.isDirectory()) walk(full);
				else if (tolerateTypes) files.push(full);
				else if (entry.isSymbolicLink()) throw new Error(`Symlink evidence entry unsupported: ${full}`);
                else if (entry.isFile()) files.push(full);
				else throw new Error(`Unsupported evidence entry: ${full}`);
			}
		}
		walk(evidencePath);
		return files.sort();
	}
	// Single file: if it's an E01 (or similar split image), collect all segments
	const ext = path.extname(evidencePath).toLowerCase();
	if (['.e01', '.ex01', '.l01', '.ad1'].includes(ext)) {
		return collectE01Segments(evidencePath);
	}
	return [evidencePath];
}

/**
 * Given disk.E01, finds disk.E01, disk.E02, … disk.E99 (up to EAA if needed)
 * that exist in the same directory.
 */
function collectE01Segments(firstSegment) {
	const dir = path.dirname(firstSegment);
	const base = path.basename(firstSegment);
	const dotIdx = base.lastIndexOf('.');
	const stem = base.slice(0, dotIdx);
	const ext = base.slice(dotIdx + 1).toUpperCase();
    const family = ext.startsWith('EX') ? 'EX' : ext.startsWith('AD') ? 'AD' : ext[0];
    // Enumerate the entire family, including gaps, mixed case and EAA overflow.
    const suffix = family === 'AD' ? /^AD[0-9]+$/i : new RegExp(`^${family}(?:[0-9]+|[A-Z]{2})$`, 'i');
    const segments = fs.readdirSync(dir).filter(name => {
        const dot = name.lastIndexOf('.');
        return name.slice(0, dot) === stem && suffix.test(name.slice(dot + 1));
    }).map(name => path.join(dir, name)).sort();
	return segments;
}

// ---------------------------------------------------------------------------
// Hash all evidence files → array of {path, sha256, sizeBytes}
// ---------------------------------------------------------------------------
async function hashEvidence(files) {
	const results = [];
	for (const f of files) {
		const stat = fs.lstatSync(f, {bigint:true});
        if (stat.isSymbolicLink()) {
            throw new Error(`Symlink evidence entry unsupported: ${f}`);
        } else if (stat.isFile()) {
            if(stat.nlink>1) throw new Error(`Hard-linked evidence unsupported: ${f}`);
            const sha256 = await sha256File(f);
            const after = fs.lstatSync(f, {bigint:true});
            if (['dev','ino','size','mtimeNs','ctimeNs','nlink','mode'].some(k => stat[k] !== after[k])) {
                throw new Error(`Evidence changed during hashing: ${f}`);
            }
            results.push({path: f, type: 'file', sha256, sizeBytes: Number(stat.size)});
        } else throw new Error(`Unsupported evidence entry: ${f}`);
	}
	return results;
}

// Canonical v1: UTF-8 JSON array of [NFC POSIX relative path, byte size, SHA-256].
// UTF-8 byte ordering is locale independent. Root identity is deliberately separate.
function evidenceRootHash(files, evidencePath, isDirectory) {
    const base = isDirectory ? evidencePath : path.dirname(evidencePath);
    const rows = files.map(f => [path.relative(base, f.path).split(path.sep).join('/').normalize('NFC'), f.sizeBytes, f.sha256]);
    rows.sort((a,b) => Buffer.compare(Buffer.from(a[0]), Buffer.from(b[0])));
    for (let i=1; i<rows.length; i++) {
        if (rows[i-1][0] === rows[i][0]) throw new Error('Ambiguous NFC evidence paths');
    }
    return crypto.createHash('sha256').update(JSON.stringify(rows), 'utf8').digest('hex');
}

function anchorRoot(logFile, rootHash, caseId, timestamp) {
    const command = process.env.LAZYNEON_WS_ANCHOR_CMD;
    if (!command) return;
    // The environment value is one executable path, never shell source.
    const result = spawnSync(command, [rootHash, caseId, timestamp], {
        shell: false, timeout: 30000, stdio: 'ignore', windowsHide: true,
    });
    appendCustodyLog(logFile, {type:'anchor', timestamp, rootHash, caseId,
        exitStatus:result.status, signal:result.signal, error:result.error?.message || null});
    if (result.error || result.status !== 0) console.warn('[미확인] anchor: 외부 기록 실패; ROOT HASH를 직접 보관하십시오.');
}

// ---------------------------------------------------------------------------
// Settings JSON builder
// ---------------------------------------------------------------------------
function buildCaseSettings(evidencePaths) {
	// evidencePaths: array of resolved paths that need read_file allow + write_file deny
	const allow = evidencePaths.flatMap((p) => [`read_file(${p})`]);
	const deny = [
		...evidencePaths.flatMap((p) => [`write_file(${p})`]),
		'download_url(*)',
		'execute_url(*)',
	];
	// Research allowlist
	for (const host of RESEARCH_URL_ALLOWLIST) {
		allow.push(`read_url(${host})`);
	}
	return {
		schemaVersion: 1,
        host: 'Antigravity / Gemini 4 Neon',
        enforcement: 'not-applied; verify host permissions before analysis',
        enableTerminalSandbox: true,
		toolPermission: 'proceed-in-sandbox',
		allowNonWorkspaceAccess: false,
		// No ask rule for read_url(*): Antigravity evaluates Deny > Ask > Allow, so an ask(*) would override
		// every allowlisted host. Unlisted hosts already fall back to Ask by default.
		permissions: {
			allow,
			deny,
		},
	};
}

// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
function printLaunchInstructions(settingsFile, caseDir) {
 console.log(`[case-mode] 케이스 작업 폴더: ${caseDir}`);
 console.log(`[case-mode] 보호 정책 제안: ${settingsFile}`);
 console.log('증거 OS 쓰기 보호를 적용했습니다. 적용 내역은 custody/hashes-start.json의 protection을 확인하십시오.');
 console.log('이 파일은 호스트 설정을 적용하거나 샌드박스를 활성화하지 않습니다.');
}

// ---------------------------------------------------------------------------
// Custody log append (append-only JSONL)
// ---------------------------------------------------------------------------
function appendCustodyLog(logPath, entry) {
	fs.appendFileSync(logPath, JSON.stringify({...entry, workspace_provenance}) + '\n', 'utf8');
}

// ---------------------------------------------------------------------------
// 'init' command
// ---------------------------------------------------------------------------
async function cmdInit(argv) {
	// Parse args: case_mode.mjs init <evidence-path> [--out <dir>]
	let evidencePath = null;
	let outDir = null;
	for (let i = 0; i < argv.length; i++) {
		if (argv[i] === '--out' && argv[i + 1]) {
			outDir = argv[++i];
		} else if (!argv[i].startsWith('--')) {
			evidencePath = argv[i];
		}
	}
	if (!evidencePath) {
		console.error('Usage: case_mode.mjs init <evidence-path> [--out <case-work-dir>]');
		process.exit(2);
	}

	const absEvidence = path.resolve(evidencePath);
	if (!fs.lstatSync(absEvidence, {throwIfNoEntry: false})) {
		console.error(`Error: evidence path not found: ${absEvidence}`);
		process.exit(1);
	}

	// Determine case work dir
	const now = new Date();
    const offset = -now.getTimezoneOffset();
    const stamp = new Date(now.getTime()+offset*60000).toISOString().slice(0,19).replace(/:/g,'-') + (offset>=0?'+':'-') + String(Math.floor(Math.abs(offset)/60)).padStart(2,'0') + String(Math.abs(offset)%60).padStart(2,'0');
	const evidenceName = path.basename(absEvidence).replace(/\.[^.]+$/, '');
	const defaultOut = path.join(path.dirname(absEvidence), `case-${evidenceName}-${stamp}`);
	const caseDir = path.resolve(outDir || defaultOut);
    if (fs.lstatSync(path.join(caseDir, 'custody', 'hashes-start.json'), {throwIfNoEntry: false})) throw new Error('Baseline already exists; use a new case directory');

    if (fs.lstatSync(path.join(caseDir,'custody','log.jsonl'), {throwIfNoEntry:false})) throw new Error('Custody log already exists; use a new case directory');
    const evidenceIsDir = fs.lstatSync(absEvidence).isDirectory();
    if (evidenceIsDir && within(canonical(caseDir),canonical(absEvidence))) throw new Error('Case working directory must be outside evidence');
    if (fs.existsSync(path.join(caseDir,'.lazyneon-workspace','case-settings.json'))) throw new Error('Case settings already exist');
    for(const rel of ['.lazyneon-workspace','custody']) {
        const output=path.join(caseDir,rel);
        if(fs.lstatSync(output,{throwIfNoEntry:false})?.isSymbolicLink() || evidenceIsDir && within(canonical(output),canonical(absEvidence))) throw new Error('Case outputs must be outside evidence; symlink output directories unsupported');
    }
    const evidenceFiles = collectEvidenceFiles(absEvidence);
    // Validate and hash before creating any working files.
    const hashes = await hashEvidence(evidenceFiles);
    const rootHash = evidenceRootHash(hashes, absEvidence, evidenceIsDir);
    const rootStat = fs.lstatSync(absEvidence, {bigint:true});
    const rootIdentity = {device:String(rootStat.dev), inode:String(rootStat.ino)};
    const caseId = path.basename(caseDir);
    const timestamp = new Date().toISOString();
	console.log(`[case-mode] Initializing case...`);
	console.log(`  Evidence : ${absEvidence}`);
	console.log(`  Case dir : ${caseDir}`);

	// Create directory structure
	const agentsDir = path.join(caseDir, '.lazyneon-workspace');
	const custodyDir = path.join(caseDir, 'custody');
	fs.mkdirSync(agentsDir, { recursive: true });
	fs.mkdirSync(custodyDir, { recursive: true });

	// Collect evidence files
	console.log(`[case-mode] Collecting evidence files...`);

	console.log(`  Found ${evidenceFiles.length} file(s)`);

	// Hash all evidence files
	console.log(`[case-mode] Computing SHA-256 hashes...`);


	// Write hashes-start.json
	const osProtection = await protection('protect', {paths: evidenceIsDir ? [absEvidence] : evidenceFiles, journal: path.join(custodyDir,'protection.jsonl')});
    try {
    const hashesStart = {
        workspace_provenance,
        rootHash, rootHashVersion: 1, rootIdentity, caseId,
        protection: osProtection,
		caseDir,
		evidencePath: absEvidence,
		timestamp,
		tool: 'case_mode.mjs init',
		note: 'SHA-256 hashes at case open — reference baseline for close verification',
		files: hashes,
	};
	const hashesFile = path.join(custodyDir, 'hashes-start.json');
	fs.writeFileSync(hashesFile, JSON.stringify(hashesStart, null, 2) + '\n', {encoding: 'utf8', flag: 'wx'});
	for(const note of osProtection.notes || []) console.warn(note);
	console.log(`[case-mode] Custody hashes written: ${path.relative(process.cwd(), hashesFile)}`);

	// Append to custody log
	const logFile = path.join(custodyDir, 'log.jsonl');
	appendCustodyLog(logFile, {
		type: 'init',
        rootHash, rootIdentity, caseId,
		timestamp: new Date().toISOString(),
		caseDir,
		evidencePath: absEvidence,
		fileCount: hashes.length,
		files: hashes,
	});

	// Build and write case-settings.json
	// Protect the declared directory or the exact single-file/segment membership.
	const protectedPaths = fs.lstatSync(absEvidence).isDirectory()
		? [absEvidence]
		: evidenceFiles;
	const settings = buildCaseSettings(protectedPaths);
	const settingsFile = path.join(agentsDir, 'case-settings.json');
	fs.writeFileSync(settingsFile, JSON.stringify(settings, null, 2) + '\n', {encoding:'utf8',flag:'wx'});
	console.log(`[case-mode] Settings written  : ${path.relative(process.cwd(), settingsFile)}`);

	// Print launch instructions
	printLaunchInstructions(settingsFile, caseDir);

	// Summary
	console.log(`[case-mode] Case initialized.`);
    console.log(`ROOT HASH: ${rootHash}`);
    console.log('이 컴퓨터 밖의 신뢰할 수 있는 곳에 ROOT HASH를 기록하고 --expect-root로 대조하십시오.');
    anchorRoot(logFile, rootHash, caseId, timestamp);
	for (const { path: p, sha256, sizeBytes } of hashes) {
		const rel = path.relative(evidenceIsDir ? absEvidence : path.dirname(absEvidence), p);
		const display = rel === '' ? path.basename(p) : rel;
		console.log(`  ${sha256.slice(0, 16)}…  ${display}  (${(sizeBytes / 1024 / 1024).toFixed(2)} MiB)`);
	}
	console.log('');
	console.log(`  case-mode close --case '${caseDir}' 를 실행하면 증거 무결성을 재검증합니다.`);
    } catch(error) {await protection('unlock',{record:osProtection});throw error;}
}

// ---------------------------------------------------------------------------
// 'close' command
// ---------------------------------------------------------------------------
async function cmdClose(argv) {
	let caseDir = null;
    let expectRoot = null;
	for (let i = 0; i < argv.length; i++) {
		if (argv[i] === '--expect-root') {
            const value = argv[++i];
            if (!value || !/^[a-fA-F0-9]{64}$/.test(value)) {
                console.error('--expect-root requires exactly 64 hexadecimal characters');
                process.exit(2);
            }
            expectRoot = value.toLowerCase();
        } else if (argv[i] === '--case' && argv[i + 1]) {
			caseDir = argv[++i];
		} else if (!argv[i].startsWith('--')) {
			caseDir = argv[i];
		}
	}

	// If not given, try CWD
	if (!caseDir) {
		caseDir = process.cwd();
	}

	const absCaseDir = path.resolve(caseDir);
	const hashesFile = path.join(absCaseDir, 'custody', 'hashes-start.json');

	if (!fs.existsSync(hashesFile)) {
		console.error(`Error: no hashes-start.json found in ${absCaseDir}/custody/`);
		console.error('  Run "case init <evidence>" first.');
		process.exit(1);
	}

	const baseline = JSON.parse(fs.readFileSync(hashesFile, 'utf8'));
	console.log('Workspace provenance: ' + JSON.stringify(workspace_provenance));
	console.log(`[case-mode] Closing case...`);
	console.log(`  Case dir : ${absCaseDir}`);
	console.log(`  Evidence : ${baseline.evidencePath}`);
	console.log(`  Opened   : ${baseline.timestamp}`);
	console.log(`  Verifying ${baseline.files.length} file(s)...`);

	const changed = [];
	const missing = [];
	const baselineMap = new Map(baseline.files.map((f) => [f.path, f]));
    const currentFiles = fs.lstatSync(baseline.evidencePath, {throwIfNoEntry: false}) ? collectEvidenceFiles(baseline.evidencePath, true) : [];
    const currentSet = new Set(currentFiles);
    const currentMap = new Map();
    let rootHash = null;
    let rootError = null;
    try {
        const stat = fs.lstatSync(baseline.evidencePath);
        const measured = await hashEvidence(currentFiles);
        for (const row of measured) currentMap.set(row.path, row);
        rootHash = evidenceRootHash(measured, baseline.evidencePath, stat.isDirectory());
    } catch (error) {rootError = error.message;}
    if (rootHash) console.log(`ROOT HASH: ${rootHash}`);
    else console.error(`ROOT HASH unavailable: ${rootError}`);
    if (!expectRoot) console.log('로컬 기록만으로는 무결성을 증명할 수 없습니다. 이 컴퓨터 밖에 보관한 ROOT HASH를 --expect-root로 제공하십시오.');
    const rootMismatch = expectRoot !== null && rootHash !== expectRoot;
    if (rootMismatch) console.error(`ROOT HASH MISMATCH — INTEGRITY FAIL: expected ${expectRoot}, actual ${rootHash ?? 'unavailable'}`);

	for (const orig of baseline.files) {
		if (!currentSet.has(orig.path)) {
			missing.push(orig.path);
			continue;
		}
        const current = currentMap.get(orig.path);
        if (!current) {changed.push({path:orig.path,type:'unverified',originalSha256:orig.sha256,currentSha256:null});continue;}
        const currentHash = current.sha256;
		if (currentHash !== orig.sha256 || current.type !== (orig.type || 'file')) {
			changed.push({
				path: orig.path,
				originalSha256: orig.sha256,
				currentSha256: currentHash,
			});
		}
	}

	// Compare the full current set, including image segments and links.
	const unexpected = [];
	if (fs.lstatSync(baseline.evidencePath, {throwIfNoEntry: false})) {
		for (const f of currentFiles) {
			if (!baselineMap.has(f)) {
				unexpected.push(f);
			}
		}
	}

    if(baseline.protection && baseline.protection.platform!==process.platform) console.warn('다른 OS — 보호 미검증; 해시로 검증합니다. 해제/재잠금은 원래 OS에서 실행하십시오.');
	const protectionProblems = baseline.protection ? await protection('verify',{record:baseline.protection}) : (console.warn('보호 미적용(구버전): 해시로 검증합니다'), []);
    for(const problem of protectionProblems) console.error(problem);
    const hasProblems = rootMismatch || rootError !== null || protectionProblems.length > 0 || changed.length > 0 || missing.length > 0 || unexpected.length > 0;

	// Append close event to custody log
	const logFile = path.join(absCaseDir, 'custody', 'log.jsonl');
	appendCustodyLog(logFile, {
		type: 'close',
        rootHash, expectRoot, rootMismatch, rootError,
		timestamp: new Date().toISOString(),
		caseDir: absCaseDir,
		evidencePath: baseline.evidencePath,
		protectionProblems,
		status: hasProblems ? 'INTEGRITY_FAIL' : 'ok',
		changed,
		missing,
		unexpected,
	});

	if (hasProblems) {
		console.error('');
		console.error('╔══════════════════════════════════════════════════════════╗');
		console.error('║  [CASE-MODE] 증거 무결성 검증 실패 — INTEGRITY FAIL     ║');
		console.error('╚══════════════════════════════════════════════════════════╝');
		if (changed.length > 0) {
			console.error(`\n  변조된 파일 (${changed.length}개):`);
			for (const c of changed) {
				console.error(`    CHANGED  ${c.path}`);
				console.error(`             원본: ${c.originalSha256}`);
				console.error(`             현재: ${c.currentSha256}`);
			}
		}
		if (missing.length > 0) {
			console.error(`\n  삭제된 파일 (${missing.length}개):`);
			for (const m of missing) {
				console.error(`    MISSING  ${m}`);
			}
		}
		if (unexpected.length > 0) {
			console.error(`\n  예상치 못한 신규 파일 (${unexpected.length}개):`);
			for (const u of unexpected) {
				console.error(`    NEW      ${u}`);
			}
		}
		console.error('');
		console.error('  증거 훼손 가능성이 있습니다. 보관 담당자에게 즉시 보고하세요.');
		console.error('');
		process.exit(1);
	} else {
		console.log('');
		console.log('  ✓ 증거 무결성 검증 완료 — 모든 파일 해시 일치');
		console.log('증거 보호 상태는 변경하지 않았습니다. 반출·삭제 전 case-mode unlock --case <case-dir> --reason <사유>');
		console.log(`    검증 파일 수: ${baseline.files.length}`);
		console.log('');
		process.exit(0);
	}
}

async function cmdUnlock(argv, action='unlock') {
    const reasonIndex=argv.indexOf('--reason');
    const reason=reasonIndex<0?'':argv[reasonIndex+1]?.trim();
    if(!reason || reason.startsWith('--')) throw new Error(action+' requires --reason');
    const ji=argv.indexOf('--journal');
    if(ji>=0) {
        if(action!=='unlock') throw new Error('--journal supports recovery unlock only');
        const journal=path.resolve(argv[ji+1]);
        appendCustodyLog(journal+'.custody.jsonl',{type:'unlock-request',timestamp:new Date().toISOString(),reason});
        await protection('unlock',{journal});
        appendCustodyLog(journal+'.custody.jsonl',{type:'unlock',timestamp:new Date().toISOString(),reason});
        console.log('Interrupted protection recovered: '+journal);return;
    }
    const i=argv.indexOf('--case');
    const caseDir=path.resolve(i<0?process.cwd():argv[i+1]);
    const mi=argv.indexOf('--manifest');
    const manifest=mi<0?path.join(caseDir,'custody/hashes-start.json'):path.resolve(argv[mi+1]);
    const baseline=JSON.parse(fs.readFileSync(manifest,'utf8'));
    if(!baseline.protection) throw new Error('No OS protection record; legacy case has hash verification only');
    // Log intent before changing protection; retain original protection baseline.
    const log=mi<0?path.join(caseDir,'custody/log.jsonl'):manifest+'.custody.jsonl';
    appendCustodyLog(log,{type:action+'-request',timestamp:new Date().toISOString(),reason});
    await protection(action,{record:baseline.protection, journal:manifest+'.'+action+'.jsonl'});
    appendCustodyLog(log,{type:action,timestamp:new Date().toISOString(),reason});
    console.log('Evidence protection '+action+': '+reason);
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------
const isMain = Boolean(process.argv[1]) && fs.realpathSync(process.argv[1]) === fs.realpathSync(fileURLToPath(import.meta.url));
if (isMain) {
	const sub = process.argv[2];
	const rest = process.argv.slice(3);
	if (sub === 'init') {
		cmdInit(rest).catch((e) => { console.error(e.message); process.exit(1); });
	} else if (sub === 'unlock' || sub === 'lock') {
        cmdUnlock(rest,sub).catch((e)=>{console.error(e.message);process.exit(1);});
	} else if (sub === 'close' || sub === 'verify') {
		cmdClose(rest).catch((e) => { console.error(e.message); process.exit(1); });
	} else {
		console.error('Usage:');
		console.error('  node scripts/case_mode.mjs init <evidence-path> [--out <case-dir>]');
		console.error('  node scripts/case_mode.mjs close|verify [--case <case-dir>] [--expect-root <hex>]');
        console.error('  node scripts/case_mode.mjs unlock|lock [--case <case-dir> | --manifest <file> | --journal <file>] --reason <reason>');
		process.exit(['--help','-h'].includes(sub) ? 0 : 2);
	}
}

export { evidenceRootHash, buildCaseSettings, collectE01Segments, collectEvidenceFiles, hashEvidence, RESEARCH_URL_ALLOWLIST };
