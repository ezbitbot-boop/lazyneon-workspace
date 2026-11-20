# LazyNeon Workspace

Version **0.1.0** · Plugin `lazyneon-workspace` · MIT

Antigravity / Gemini 4 Neon용 독립 포렌식·한국어 문서·법률 초안 companion 플러그인.
모델 라우팅과 일반 가드는 LazyNeon core 소유다. 도메인 규칙은 [rules/GEMINI.md](rules/GEMINI.md)를 따른다.

## 설치와 실행

이 디렉터리를 호스트의 플러그인 등록 기능으로 등록한다. 다른 플러그인의 설치·탐지·업데이트는 수행하지 않는다.
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

케이스의 `close`는 증거 잠금을 유지합니다. 반출·삭제 전에는
`case-mode unlock --case <작업폴더> --reason "인계 사유"`로 해제합니다.
해제 후 검증을 재개할 때는 `case-mode lock --case <작업폴더> --reason "재개 사유"`로
재잠금한 다음 `close`를 실행합니다. 재잠금은 최초 파일 신원·해시·원래 권한을 바꾸지 않습니다.

`lazyforensic manifest <폴더> [-o manifest.json]`는 기본적으로 읽기만 합니다.
잠금이 필요하면 `--protect -o manifest.json`을 명시하고, 해제에는
`case-mode unlock --manifest manifest.json --reason "사유"`를 사용합니다.
읽기 전용 매체는 `protected-by-media`, immutable/ACL 미지원 파일시스템은
`not-lockable`로 기록합니다. 후자는 적용된 보호만 검사하며 해시·파일 목록 검증은 계속합니다.
다른 OS로 옮긴 케이스는 보호 미검증 경고와 함께 해시를 검사하고, 해제·재잠금은 원래 OS에서 수행합니다.

초기화가 중단되어 기준선이 아직 없으면 `custody/protection.jsonl`의 변경 전 기록으로
`case-mode unlock --journal <protection.jsonl> --reason "중단 복구"`를 실행할 수 있습니다.
manifest 보호 중단 기록은 `<manifest.json>.protection.jsonl`입니다.

## 외부 루트 해시로 검증하는 무결성 모델

증거 보호는 best-effort 예방이다. 에이전트는 소유자와 같은 OS 사용자로 실행되므로
증거 파일과 로컬 기준선·감사 로그를 함께 바꿀 수 있다. 로컬 기록만으로는 무결성을 증명할 수 없다.
`case-mode init`이 출력한 `ROOT HASH: <hex>`를 즉시 **이 컴퓨터 밖**의 신뢰할 수 있는 곳에 보관한다.
외부 보관한 값으로 `case-mode close --case <작업폴더> --expect-root <hex>` 또는
`case-mode verify --case <작업폴더> --expect-root <hex>`를 실행한다.
실제 증거에서 재계산한 값이 다르면 로컬 기록과 무관하게 실패한다.
옵션을 생략하면 재계산값과 로컬 검증의 한계를 출력한다.

해시 형식 v1은 `[상대경로, 바이트 크기, 파일 SHA-256]` 행 배열의 공백 없는 UTF-8 JSON에 대한 SHA-256이다.
상대경로는 `/` 구분자와 NFC 정규화를 적용한 뒤 UTF-8 바이트 순으로 정렬하며, 정규화 충돌은 거부한다.
폴더는 그 루트 기준, 단일 파일·이미지 세그먼트는 부모 기준이다.
루트 device/inode는 `rootIdentity`에 문자열로 기록하지만 해시에서는 제외한다.
시간·절대경로·case id·권한도 해시에 포함하지 않는다.

선택적으로 `LAZYNEON_WS_ANCHOR_CMD`에 **실행파일 하나의 경로**를 설정한다(공백 있는 경로 허용).
init은 셸 없이 `[ROOT HASH, case id, UTC ISO 시각]` 세 인자로 한 번 실행한다.
case id는 작업 폴더 basename이며 시각은 기준선 timestamp와 같다.
추가 고정 인자가 필요하면 별도 실행파일을 작성한다. 30초 제한, 실행 실패·비정상 종료는
custody 로그에 exitStatus(실행 불가 시 null)·signal·error를 기록하고 `[미확인] anchor`를 출력하지만 init을 실패시키지 않는다.
성공 종료만으로 외부 보관 완료가 증명되지는 않으므로 외부 수신 기록을 확인한다.

검증은 신뢰할 수 있는 도구·실행 환경에서 외부 보관값과 대조해야 한다. SHA-256의 충돌 저항성을 전제로
측정 시점의 파일 집합·이름·크기·내용 변경을 탐지한다. 변경 후 원상복구한 이력이나
검증 프로그램 자체가 변조된 환경까지 탐지한다고 주장하지 않는다.
보고서 무결성 절에는 실제 ROOT HASH와 외부 보관·대조 결과를 적는다.

### 수동 업데이트 및 실행 출처

SessionStart는 최대 24시간에 한 번 짧은 제한시간으로 origin의 main ref만 조회합니다. 로컬 객체로 선후 관계가 확인되면 한 줄 `update available` 안내를 표시합니다. 원격 커밋 객체가 없으면 `update available`에 선후 관계 미확인임을 함께 표시합니다. 자동 fetch/pull 및 코드 변경은 없습니다. 확인 시각은 사용자 `~/.cache/lazyneon-workspace`에 저장합니다. `LAZYNEON_OFFLINE=1` 또는 `LAZYNEON_WS_NO_UPDATE_CHECK=1`이면 확인하지 않습니다.

로컬 변경(미추적 파일 포함)이 있으면 거부하는 수동 업데이트 한 줄 (`<plugin>`을 설치 경로로 교체):

```sh
p='<plugin>'; s=$(git -C "$p" status --porcelain --untracked-files=normal) && { if [ -z "$s" ]; then git -C "$p" pull --ff-only; else echo 'Refusing update: local changes' >&2; false; fi; }
```

`python scripts/workspace_provenance.py`는 설치된 Workspace의 버전·Git 커밋·dirty 여부를 반환합니다. 보고서 작성 시 출력값을 기록하고, 검증 시점의 출처와 구분하여 보존합니다. Git 없는 배포본의 커밋/dirty 값은 `unknown`입니다.
