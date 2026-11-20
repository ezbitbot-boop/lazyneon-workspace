import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {isCoreOwned} from '../scripts/hook_targets.mjs';
const read = p => fs.readFileSync(new URL('../'+p, import.meta.url),'utf8');
const journals=['brief.md','claim-graph.md','intent-diff.md','observation-manifest.md','verification-economics.md','cause-disappearance.md','excursion-log.md','expansion-log.md','sources-ledger.md','debate-log.md','scope.md','plan.md','outcome.json','verify-step.md'];
test('improve2 final deliverables and source files are not core state',()=>{
 for(const name of ['report.md','report.html','SYNTHESIS.md','sources/report.md','sources/raw.txt'])
  assert.equal(isCoreOwned('.lazyneon/ulw-research/s/'+name),false,name);
 for(const name of journals) assert.equal(isCoreOwned('.lazyneon/ulw-research/s/'+name),true,name);
 for(const name of ['pins.md','ulw-scope.md','ulw-dag.json','lookups.jsonl','feedback/s.jsonl','feedback/s.jsonl.123.taking','logs/s.log','logs/s.jsonl']) assert.equal(isCoreOwned('.lazyneon/'+name),true,name);
});
test('improve2 one exhaustive exclusion reference matches executable patterns',async()=>{
 const {CORE_OWNED_PATHS}=await import('../scripts/hook_targets.mjs');
 assert.ok(Array.isArray(CORE_OWNED_PATHS));
 const doc=read('docs/domain-targets.md');
 const block=doc.split('<!-- core-owned-paths:start -->')[1]?.split('<!-- core-owned-paths:end -->')[0];
 assert.ok(block);
 assert.deepEqual([...block.matchAll(/^- `([^`]+)`$/gm)].map(m=>m[1]),CORE_OWNED_PATHS);
 for(const pattern of CORE_OWNED_PATHS){
  const sample=pattern.replaceAll('<session>','s').replaceAll('<name>','x').replaceAll('<PID>','123').replaceAll('*','step');
  assert.equal(isCoreOwned('.lazyneon/'+sample),true,sample);
  assert.equal(isCoreOwned('.lazyneon/'+sample+'.backup'),false,sample);
 }
 for(const file of ['README.md','GEMINI.md']){
  const body=read(file);assert.match(body,/\[도메인 가드 대상\]\(docs\/domain-targets\.md\)/);
  assert.doesNotMatch(body,/ulw-research\/<session>|세션 저널\(`/);
  for(const line of body.split('\n').filter(line=>/제외|exempt|excluded/i.test(line))) {
   assert.doesNotMatch(line,/`[^`]*(?:\.lazyneon\/|\.(?:md|html|json|jsonl)|\*\*)[^`]*`/,file+': use the canonical exclusion reference');
  }
  for(const name of journals) assert.ok(!body.includes('`'+name+'`'),file+': duplicate '+name);
 }
});
test('improve2 workspace contract attributes core context loading to core',()=>{
 assert.match(read('GEMINI.md'),/두 파일의 읽기·주입은 core SessionStart가 담당/);
 assert.doesNotMatch(read('GEMINI.md'),/는 있을 때만 읽는다/);
 assert.equal(read('rules/GEMINI.md'),read('GEMINI.md'),'host rules must carry the same contract');
});
const skills=['lazyforensic','sqlite-evidence-query','korean-doc-parser'];
for(const skill of skills) test('improve2 decoy checklist: '+skill,()=>{
 const body=read(`skills/${skill}/SKILL.md`).split('## AI decoy / anti-analysis trap')[1]?.split('\n## ')[0];
 assert.ok(body,'artifact analysis entrypoint needs checklist');
 for(const term of ['가설','SHA-256','격리','실행 추적','포맷 파서','[미확인]','소스맵','opaque predicate','shadow state machine','WASM','SQLite','API 키','비활성 섹션','예산','nothing found']) assert.ok(body.includes(term),term);
});
test('improve2 workspace release is consistently 0.2.1',()=>{
 for(const file of ['package.json','plugin.json']) assert.equal(JSON.parse(read(file)).version,'0.2.1');
 for(const file of ['README.md','GEMINI.md','scripts/session_start.mjs']) assert.ok(read(file).includes('0.2.1'),file);
 assert.match(read('CHANGELOG.md'),/## 0\.2\.1/);
});
