// Only structured fields affect classification; diagnostic prose is untrusted data.
export function classifyGuardResult(result) {
  if (result.error || result.signal) return {kind:'unchecked',message:'[미확인] 검증 미완료 (timeout/crash/unavailable)'};
  let verdict={};
  for (const line of (result.stdout||'').split('\n')) { try { const parsed=JSON.parse(line); verdict=parsed && typeof parsed==='object' && !Array.isArray(parsed)?parsed:{}; } catch {} }
  if (['TIMEOUT','CRASH'].includes(verdict.code)) return {kind:'unchecked',message:'[미확인] 검증 미완료 (timeout/crash/unavailable)'};
  if(verdict.status==='FAIL') return {kind:'fail',message:'FAIL: 도메인 검증 실패'};
  if (verdict.code==='MORPH_UNAVAILABLE') return {kind:'unchecked',message:'[미확인] 형태소 엔진 없음: kiwipiepy 설치 후 재검증 필요'};
  if(verdict.status==='NOT_CHECKED') return {kind:'unchecked',message:'[미확인] 검증기 실행 불가 또는 결과 없음'};
  if(verdict.status==='FAIL' || ['block','deny'].includes(verdict.decision)) return {kind:'fail',message:'FAIL: 도메인 검증 실패'};
  if(result.status!==0) return {kind:'unchecked',message:'[미확인] 검증기 비정상 종료'};
  if(verdict.status==='WARN') return {kind:'warn',message:'WARN: 도메인 검증 경고'};
  if(verdict.status==='PASS') return {kind:'pass',message:'PASS'};
  if(verdict.status==='NOT_APPLICABLE') return {kind:'pass',message:'NOT_APPLICABLE'};
  return {kind:'unchecked',message:'[미확인] 명시적 검사 결과 없음'};
}
