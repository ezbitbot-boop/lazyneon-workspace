# LazyNeon Workspace 0.1.0

호스트: Antigravity, Gemini 4 Neon. 모델 라우팅은 LazyNeon core가 소유하며 이 플러그인은 정의하지 않는다.
증거 분석·한국어 문서·법률 초안의 독립 도메인 플러그인이다. 포렌식 획득 또는 법원 제출 적격성을 보장하지 않는다.

## 코어 계약

- `.lazyneon/` 및 write_chunk, markdown_structure, json_schema, stop_claim, lookup, selfcheck, post_tool_feedback 가드는 코어 소유다.
- 고정 식별자 `.lazyneon/pins.md`, 범위 잠금 `.lazyneon/ulw-scope.md`는 있을 때만 읽는다. 이 플러그인은 두 파일을 생성·수정하지 않는다.
- 자체 상태·고정 식별자·감사 로그는 `.lazyneon-workspace/`, 자체 환경변수는 `LAZYNEON_WS_*`를 쓴다.
- 다른 플러그인을 탐지하지 않는다. 세션 시작은 도메인 요약만 제공하며 자동 업데이트하지 않는다.
- evidence_guard, hallucination_guard, legal_factuality_guard, slop_guard만 도메인 가드로 등록한다.
- 사후 가드는 이미 수행된 쓰기를 되돌리지 않는다. FAIL은 수정·재검증 전 제출 금지를 뜻한다. 실제 호스트 이벤트 전달은 별도 실연동 검증이 필요하다.
- 사용 가능한 호스트 도구 스키마를 확인한다. 이 플러그인은 서브에이전트 호출 형식이나 모델 역할을 강제하지 않는다.
- 큰 문서는 100줄 이하 청크로 편집하고 원문을 재열람한다.

## 실패 폐쇄 (할루시네이션 차단 — 최우선)

- `--input` 없으면 샘플 USB/카카오 유출 사건을 만들지 않는다.
- 파일·로그 없으면 빈칸 또는 `미확인`/`미측정`으로 두며 이벤트·해시·시각을 만들지 않는다.
- Windows 복사의 `생성시각 > 수정시각`을 Timestomping으로 단정하지 않는다.
- 카카오 파서는 `.txt` 내보내기만 지원한다(SQLite 직접 파싱 금지).
- 선택 법령 원문 조회 도구가 없으면 그 사실만 알리고 조문을 창작하지 않는다.
- 금지 문구: "명백히 입증", "법원에 유효", "유출 확정", "court-admissible", "Timestomping으로 단정".
- 증거 오디오는 명시적 `--upload-audio` 동의 없이 외부 전송 금지.
- **근거-결론 분리**: 모든 수치·해시·시각·조문은 스크립트 stdout / MCP 응답에만 근거하며 없으면 `미확인` 처리한다.
- **결측 비율**: `verify_report.py`의 `unverified.ratio`가 수치·해시·시각의 절반 초과 시 WARN(`--strict`는 FAIL)이며 사유(증거 부재 / 모델 유보 / 도구 미설치)를 적는다.
- **감사 수치**: "N개 중 M개 결함" 결론은 직접 연 `파일:라인`과 실행 출력에만 근거한다.
- **SPA 채증**: 표준/ARIA 셀렉터를 쓰고 네비게이션 직후 `waitForLoadState`/`waitForSelector` 안정화 뒤 조작한다.
- **커버리지 수신증**: "전수/100% 커버리지" 주장은 `node scripts/coverage_audit.mjs --source <원문파일> --target <산출물…> --json <수신증.json>` 출력으로만 뒷받침한다(`--source` 필수).
- **부모 검증 & High-Fidelity**: `forensic-report` 초안은 분석 담당자가 `python scripts/verify_report.py <보고서> --evidence <audit.json> --morph-grounding --high-fidelity`로 재검증한다(`<evidence>` 누락·형태소 커버리지 70% 미달·`FAIL` 시 제출 금지). `.lazyneon-workspace/pins.md`·`.lazyneon-workspace/ulw-scope.md` 및 `.lazyneon/ulw-research/<session>/`의 명시된 세션 저널(`brief.md`, `claim-graph.md`, `intent-diff.md`, `observation-manifest.md`, `verification-economics.md`, `cause-disappearance.md`, `excursion-log.md`, `expansion-log.md`, `sources-ledger.md`, `debate-log.md`)은 `hallucination_guard.mjs`에서 제외한다.
- **컴팩션 요약 불신 및 볼륨 시리얼 대조**: `<CONTEXT_SUMMARY>`는 인접 행 `hit_id`·`artifact_name`을 오염시키므로 인용 전 `query_evidence_db.py --verify-hits/--verify-report`(`verify_report.py --axiom-db`)와 `.lazyneon-workspace/pins.md`로 재검증한다. 다중 디스크 환경은 볼륨 시리얼과 구 드라이브 후속 입출력 대조 전까지 드라이브 문자 변경으로 단정하지 않는다.


- 모델 거부·유보는 `미확인(모델 유보: 사유)`로 기록한다. 민감 증거 원문은 스크립트가 다룬다.
- 전사는 로컬 또는 사용자가 승인한 서버 방식만 사용한다. 서버 음성 전송 기본값은 꺼짐이다.
- 개인정보는 작업에 필요한 최소 범위로 처리하고 원본·마스킹 사본·대응표를 분리 보관한다.

## 스킬 라우팅

보고서·검토해줘·검증 요청은 무조건 report-guard의 verify_report.py 및 hallucination_guard 검증을 거친다.
도움말은 docs/USER_GUIDE.md를 참고한다. 다음 21개 스킬만 활성화한다.

- `skills/court-evidence-stamper/SKILL.md`
- `skills/court-pdf-binder/SKILL.md`
- `skills/evidence-integrity-audit/SKILL.md`
- `skills/financial-flow-tracer/SKILL.md`
- `skills/korean-pii-masker/SKILL.md`
- `skills/case-mode/SKILL.md`
- `skills/court-ruling-analyzer/SKILL.md`
- `skills/deepfake-forensic-radar/SKILL.md`
- `skills/forensic-audit/SKILL.md`
- `skills/forensic-report/SKILL.md`
- `skills/forensic-timeline/SKILL.md`
- `skills/forensic-video/SKILL.md`
- `skills/humanize-korean/SKILL.md`
- `skills/kakao-chat-extractor/SKILL.md`
- `skills/korean-doc-parser/SKILL.md`
- `skills/lazyforensic/SKILL.md`
- `skills/legal-draft-builder/SKILL.md`
- `skills/media-analysis/SKILL.md`
- `skills/report-guard/SKILL.md`
- `skills/sqlite-evidence-query/SKILL.md`
- `skills/telegram-chat-extractor/SKILL.md`

비전 판독은 텍스트 증거가 아니다. 이미지의 글자·수치는 OCR 출력과 대조하고 미검증 모델 판독은 따로 표시한다.
