# Changelog

## Unreleased

- evidence_guard: 폴더 이름 `evidence` 검사를 작업 폴더 기준 경로에만 적용. `…/Evidence/case1` 같은 상위 폴더 이름 때문에 모든 쓰기가 막히던 문제 수정. 작업 폴더 밖 경로와 이름이 evidence인 작업 폴더는 계속 차단.
- evidence_guard: 검사 중 예외가 나면 명시적으로 deny. Windows에서 glob 쓰기 대상을 펼치지 못하던 문제 수정.
- domain_feedback: 전달한 판정 큐는 바로 삭제하고, 전달되지 않은 큐는 24시간 뒤 삭제.
- README: Windows PowerShell 업데이트 명령 추가.
- 네 도메인 가드의 stdin 읽기 함수를 `hook_workspace.mjs` 하나로 통합(동작 변화 없음).
- case-mode Windows 증거 보호: `icacls /deny (W,D,DC)`는 SYNCHRONIZE까지 막아 증거 읽기·목록이 실패하고 close/verify가 깨졌음. 특정 권한 `(WD,AD,WEA,WA,DE,DC)` deny와 읽기 전용 속성으로 바꿔 쓰기·생성·삭제·이름 변경·밖으로 이동·읽기 전용 해제(`del /f`, `Remove-Item -Force` 포함)는 막고 읽기·목록은 허용. verify는 정확히 이 deny 집합과 읽기 전용 속성이 모두 있어야 통과.
- GitHub Actions: Node 20–25 × 3 OS 계약 테스트, Python 3.12 × 3 OS pytest.

## 0.2.2 — 2026-11-26

- evidence_guard: glob 쓰기 대상이 증거와 겹치면, 증거가 있는 작업 폴더에서 인라인 인터프리터(`node -e`, `python -c` 등)가 계산된 경로를 쓰거나 지우면, ffmpeg의 가운데 출력 인자가 증거면 거부.
- 출력 경로가 증거 파일의 하드링크면 거부(`safe_output` inode 비교), 매니페스트는 임시 파일 후 원자적 교체로 저장.
- mask_korean_pii: 입력·출력·리포트·vault 경로(또는 inode)가 겹치면 거부. vault는 0600으로 원자적 생성.
- 보고서 검증: 재계산한 케이스 ROOT HASH가 기준선 `rootHash`와 다르면 실패.
- case-mode close: custody 로그에 맞는 개시 기록이 없으면 `CUSTODY INCOMPLETE`로 실패(해시 결과와 따로 보고).
- unlock: 모든 항목의 dev/ino를 먼저 확인하고, 교체·누락이 있으면 아무것도 바꾸지 않고 "복구 불완전"으로 실패.
- evidence_manifest 생성: lstat으로 열거하고 심볼릭 링크는 거부.

## 0.2.1 — 2026-11-20

- core 제외 경로를 실행 목록과 문서 대조로 단일화하고 README·GEMINI는 정본을 참조.
- 연구 최종 보고서·SYNTHESIS 및 sources 파일의 core 상태 면제 제거; 작업 저널·예약 상태 면제 유지. SYNTHESIS 파일명도 환각 가드의 최종 보고서로 인식.
- pins/scope 읽기·주입 주체가 core임을 명시.
- 아티팩트 라우터·SQLite·패키지 문서 분석 스킬에 AI 미끼와 예산 소진 보고 체크리스트 추가.

## 0.2.0 — 2026-11-20

- `requires: lazyneon >=0.3.0`: 형제 plugin.json을 읽는 SessionStart/doctor companion 진단. core 미설치 시 매 세션 경고, 미설치·비호환은 비차단 WARN.
- macOS/Windows install-both 절차 및 두 플러그인의 훅 순서·결합 계약·통합 시뮬레이터 문서화.
- 모든 도메인 스킬에서 PII·증거·보안/포렌식 작업의 Hydrogen 전 계열 사용 금지, 병렬 작업자는 Neon. core injection pre-filter 선행 지침.
- Windows 드라이브/UNC 증거 출력 경계 정규화. 매니페스트에서 `__pycache__` 이름의 증거도 포함하고 검증.
- Windows Python 선택기를 공통화하고 실행/3.12 버전 probe·후보 fallback·3초 제한·명시적 py 버전 선택 추가.
- case close/verify는 파일별 해시를 한 번 계산해 루트 해시와 변경 목록에 재사용. 해싱 중 메타데이터 변화는 실패 처리.
- 업데이트 알림 잠금에 PID·시각 기록, 만료된 죽은 소유자 잠금 회수 및 전체 Git 시간 예산 적용.
- 한국어 규칙의 실제 적용 범위 명시. domain_feedback 미사용 지역 변수 정리.

### 0.1.0 이후 도입되었으나 이력이 없던 기능

- 외부 보관 ROOT HASH와 `--expect-root` 검증, NFC/UTF-8 정렬·충돌 거부, 선택적 anchor 실행·실패 기록.
- issuer 설정 예제와 실행 시 설정 읽기, PII 마스킹 기관 예외의 명시적 설정.
- 수동 업데이트 안내, SessionStart의 24시간 ref 조회 알림과 offline opt-out.
- 보고서·매니페스트에 Workspace 실행 버전/Git 출처 기록.
- 독립 `.lazyneon-workspace` 상태와 21개 활성 도메인 스킬, core 일반 가드와 분리된 4개 도메인 가드.
- 증거 OS 보호·unlock/lock 기록, 외부 전사 명시적 동의, 실험 기능 비활성화 및 기존 NOTICE 보존.

## 0.1.0

- LazyNeon Workspace 독립 배포 기준 버전. 당시 변경 이력 파일은 없었으며, 위 항목의 개별 도입 일자는 소급 확정하지 않는다.
