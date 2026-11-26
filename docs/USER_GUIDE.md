# LazyNeon Workspace

Version **0.2.0** · Plugin `lazyneon-workspace` · MIT

Antigravity / Gemini 4 Neon용 독립 포렌식·한국어 문서·법률 초안 companion 플러그인.
모델 라우팅과 일반 가드는 LazyNeon core 소유다. 도메인 규칙은 [rules/GEMINI.md](rules/GEMINI.md)를 따른다.

## 설치와 실행

이 디렉터리를 호스트의 플러그인 등록 기능으로 등록한다. 형제 폴더에서 core 이름·버전을 읽기 전용 확인하며 자동 설치·업데이트하지 않는다.
Python 3.12+, Node 20+가 필요하다. `python3 scripts/setup_forensic_env.py`로 공통 venv에 requirements.txt와 선택 의존성을 설치한다.
CLI와 가드는 `LAZYNEON_WS_PYTHON` → 저장소 `.venv` → `~/.lazyneon-workspace/venv` → 시스템 Python 순으로 사용한다.
`LAZYNEON_WS_LEGACY_PYTHON`은 기존 설정 호환용 별칭이며 새 설정에는 `LAZYNEON_WS_PYTHON`을 사용한다.
`bin/lazyforensic`는 유지 스킬이 사용하는 CLI이다. `bin/lazyothers`는 문서 처리 CLI이다.
외부 서비스 실연동과 Gemini 4 Neon의 윤문 품질은 아직 검증되지 않았다.

## Windows (PowerShell)

Python 3.12+와 Node 20+ 설치 후 `python scripts/setup_forensic_env.py`를 실행한다.
기본 ExecutionPolicy가 Restricted여도 `.cmd` 래퍼는 해당 실행에만 Bypass를 적용한다.
직접 실행 예: `powershell -NoProfile -ExecutionPolicy Bypass -File bin\lazyforensic.ps1 verify report.md`.
`bin\lazyforensic.cmd`, `bin\lazyothers.cmd`, `bin\case-mode.cmd`도 사용할 수 있다.
설치된 인터프리터 지정: `$env:LAZYNEON_WS_PYTHON = "C:\Python312\python.exe"`.

kordoc MCP는 Node/npx가 필요하며 최초 패키지 설치에는 npm 레지스트리 네트워크 접속이 필요하다.
문서 파서는 실행 중 npx 패키지를 자동 설치하지 않는다. 의존성 설치는 별도로 수행한다.

## 코어와 상태

`.lazyneon/` 전체를 제외하지 않는다. core 예약 상태 경로와 `.lazyneon/ulw-research/<session>/{SYNTHESIS.md,report.md,report.html,verify-*.md,sources/**}`만 검증·차단·해시 감사에서 제외한다. 그 밖의 사용자 파일은 검사한다.
자체 상태는 `.lazyneon-workspace/`, 환경변수는 `LAZYNEON_WS_*`에 둔다.
등록된 도메인 가드는 evidence_guard, hallucination_guard, legal_factuality_guard, slop_guard다.
사후 실패는 원본을 복구하는 기능이 아니며, 수정·재검증 전 결과 제출을 금지한다.

## 활성 스킬

| 스킬 | 승인 상태 |
| --- | --- |
| [court-evidence-stamper](skills/court-evidence-stamper/SKILL.md) | KEEP |
| [court-pdf-binder](skills/court-pdf-binder/SKILL.md) | KEEP |
| [evidence-integrity-audit](skills/evidence-integrity-audit/SKILL.md) | KEEP |
| [financial-flow-tracer](skills/financial-flow-tracer/SKILL.md) | KEEP |
| [korean-pii-masker](skills/korean-pii-masker/SKILL.md) | KEEP |
| [case-mode](skills/case-mode/SKILL.md) | KEEP-AFTER-FIX |
| [court-ruling-analyzer](skills/court-ruling-analyzer/SKILL.md) | KEEP-AFTER-FIX |
| [deepfake-forensic-radar](skills/deepfake-forensic-radar/SKILL.md) | KEEP-AFTER-FIX |
| [forensic-audit](skills/forensic-audit/SKILL.md) | KEEP-AFTER-FIX |
| [forensic-report](skills/forensic-report/SKILL.md) | KEEP-AFTER-FIX |
| [forensic-timeline](skills/forensic-timeline/SKILL.md) | KEEP-AFTER-FIX |
| [forensic-video](skills/forensic-video/SKILL.md) | KEEP-AFTER-FIX |
| [humanize-korean](skills/humanize-korean/SKILL.md) | KEEP-AFTER-FIX |
| [kakao-chat-extractor](skills/kakao-chat-extractor/SKILL.md) | KEEP-AFTER-FIX |
| [korean-doc-parser](skills/korean-doc-parser/SKILL.md) | KEEP-AFTER-FIX |
| [lazyforensic](skills/lazyforensic/SKILL.md) | KEEP-AFTER-FIX |
| [legal-draft-builder](skills/legal-draft-builder/SKILL.md) | KEEP-AFTER-FIX |
| [media-analysis](skills/media-analysis/SKILL.md) | KEEP-AFTER-FIX |
| [report-guard](skills/report-guard/SKILL.md) | KEEP-AFTER-FIX |
| [sqlite-evidence-query](skills/sqlite-evidence-query/SKILL.md) | KEEP-AFTER-FIX |
| [telegram-chat-extractor](skills/telegram-chat-extractor/SKILL.md) | KEEP-AFTER-FIX |

## 비활성 실험 기능

`experimental/video-editor/`와 `experimental/web-evidence-capture/`는 파일만 보존하며 자동 발견·라우팅·MCP 등록에서 제외한다.
활성화 전 편집·렌더링 또는 브라우저 채증 전체 흐름을 검증해야 한다.

## 검증과 한계

`python -m pytest`는 pytest 설정의 `not kakao` 마커와 수집 제외 규칙을 적용한다.
`node --test test/workspace_contract.test.mjs`로 Node 계약 테스트를 실행한다.
kakao라는 이름을 포함한 테스트·스크립트 실행은 소유자 규칙상 금지한다. 다른 테스트 파일의 내부 호출도 확인해야 한다.
HWP5 OLE 경로에는 `olefile`이 필요하다. 미설치 시 설치 안내 오류를 반환한다.
네트워크 STT는 `--upload-audio` 명시적 동의가 필요하며, 실제 서버 전사는 이번 검증에 포함하지 않는다.
삭제 목록과 참조 검토는 `docs/review/`에 보존한다. MIT 출처 및 기존 기록은 [NOTICE](NOTICE)에 보존한다.

## 설명서: 보고서 완성 워크플로
원본 해시를 측정하고 파싱한 뒤 보고서를 작성하고 verify_report.py로 대조한다.
타임라인은 `python skills/forensic-timeline/scripts/generate_timeline.py --input events.json --output timeline.html`로 만든다.
HTML 표현은 인라인 CSS를 사용하고 페이지 출력·글자 누락을 검수한다.

미디어 단서 분석: `python scripts/analyze_deepfake_evidence.py <미디어>`. C2PA 바이트 표식은 암호학적 서명 검증 결과가 아니다.

### 도메인 훅 피드백 계약

PostToolUse는 항상 `{}`와 exit 0을 반환한다. 가드별 판정은 생성 즉시
`~/.lazyneon-workspace/feedback/<sha256(conversationId)>.jsonl`에 기록하고,
PreInvocation이 실패·경고를 JSON으로 인용한 `ephemeralMessage`로 전달한 뒤 그 큐 파일을 지운다.
판정에는 사건 파일 경로가 들어가므로 전달되지 않은 큐도 24시간이 지나면 다음 훅 실행 때 지운다.
도구 결과와 파일 원문은 피드백에 포함하지 않는다. 큐 위치는 workspacePaths/cwd 유무와
무관하다. 대화 ID는 conversationId, conversation_id, session_id 순서로 선택하며
모두 없으면 `unidentified` 키를 사용한다. 이 경우 호스트가 대화를 구분할 수 없다.
상대 대상 경로는 호스트 workspace 우선, 없으면 훅 프로세스 cwd 기준으로 확정한다.
이 폴백은 피드백/대상 해석용이며 케이스 감사 위치를 추측하지는 않는다.

전체 relay 예산은 115초(등록된 125초 timeout보다 짧음)이며
`LAZYNEON_WS_FEEDBACK_BUDGET_MS`로 더 짧게 설정할 수 있다. 시간 초과·충돌·
미검증 대상은 `[미확인]` 실패로 기록한다. 법률 검증의 개별 timeout은 최대 25초이며
`LAZYNEON_WS_VERIFY_TIMEOUT_MS`로 줄일 수 있다. stdout/stderr 원문 대신
가드 이름, 대상 경로, PASS/FAIL/WARN/미확인 판정만 보존한다.

설치 조합·한국어 규칙 적용 범위·Windows Python 선택 정책은 [README](../README.md),
훅 결합 계약은 [hook-coexistence](hook-coexistence.md)를 따른다.
