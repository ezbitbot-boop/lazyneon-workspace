# Workspace 도메인 가드 대상

`hookTargetOperations()`는 패치의 쓰기·삭제·이동 출발지·이동 목적지를 구분한다.
PreToolUse 증거 보호는 `hookTargets()`로 **모든** 경로를 검사한다.
PostToolUse relay와 직접 실행하는 내용 가드는 `contentTargets()`로 쓰기와
이동 목적지만 검사한다. 삭제·이동 출발지는 검사 제외이며 PASS로 가장하거나
실패 메시지로 주입하지 않는다. 읽기 명령과 읽기 MCP 도구에는 판정을 기록하지 않는다. 쓰기 가능한 호출의 목적지를 알 수 없을 때만 `unchecked` / `[미확인]`을 기록한다. 미검사는 PASS도 FAIL도 아니다. `python gen.py`처럼 임의 스크립트 실행은 출력 경로가 없으면 미확인으로 남는다.

`.lazyneon/` 전체를 제외하지 않는다. core 예약 상태 경로와 `.lazyneon/ulw-research/<session>/{brief.md,claim-graph.md,intent-diff.md,observation-manifest.md,verification-economics.md,cause-disappearance.md,excursion-log.md,expansion-log.md,sources-ledger.md,debate-log.md,scope.md,plan.md,outcome.json,SYNTHESIS.md,report.md,report.html,verify-*.md,sources/**}`만 검증·차단·해시 감사에서 제외한다. 그 밖의 사용자 파일은 검사한다.
경로는 심볼릭 링크를 해석하며, 아직 없는 파일의 나머지 경로도 유지한다.

| `.lazyneon/` 기준 경로 | 제외 근거 |
| --- | --- |
| `pins.md` | core `session_start.mjs`가 읽는 고정 식별자 상태 |
| `ulw-scope.md` | core `session_start.mjs`와 `doctor.mjs`가 읽는 범위 잠금 상태 |
| `ulw-dag.json` | core `stop_claim_guard.mjs`가 읽는 작업 DAG 상태 |
| `lookups.jsonl` | core `lookup_guard.mjs`가 쓰는 조회 기록 |
| `feedback/<이름>.jsonl`, `feedback/<이름>.jsonl.<PID>.taking` | core `post_tool_feedback.mjs`의 대화별 큐와 원자적 읽기용 임시 이름 |
| `logs/<이름>.log`, `logs/<이름>.jsonl` | 로그용으로 예약한 직속 기계 기록 형식; 사용자 요청의 logs 제외 범위를 이 형식으로 한정 |

`lookups/`, `feedback/`, `logs/` 디렉터리 전체를 제외하지 않는다.
예를 들어 `ulw-research/report.md`, `feedback/report.md`, `logs/report.txt`,
`evidence/disk.raw`는 다른 도구가 쓰는 일반 산출물·증거와 동일하게 검사한다.
`pins.md.backup` 같은 접미사 변형도 제외하지 않는다. 위 목록은 경로에 따른
예약 상태 계약이며 작성 도구의 신원을 인증하는 기능은 아니다.
