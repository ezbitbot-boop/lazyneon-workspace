# Workspace 도메인 가드 대상

`hookTargetOperations()`는 패치의 쓰기·삭제·이동 출발지·이동 목적지를 구분한다.
PreToolUse 증거 보호는 `hookTargets()`로 **모든** 경로를 검사한다.
PostToolUse relay와 직접 실행하는 내용 가드는 `contentTargets()`로 쓰기와
이동 목적지만 검사한다. 삭제·이동 출발지는 검사 제외이며 PASS로 가장하거나
실패 메시지로 주입하지 않는다. 읽기 명령과 읽기 MCP 도구에는 판정을 기록하지 않는다. 쓰기 가능한 호출의 목적지를 알 수 없을 때만 `unchecked` / `[미확인]`을 기록한다. 미검사는 PASS도 FAIL도 아니다. `python gen.py`처럼 임의 스크립트 실행은 출력 경로가 없으면 미확인으로 남는다.

`.lazyneon/` 전체를 제외하지 않는다. 아래 목록은 `scripts/hook_targets.mjs`의
`CORE_OWNED_PATHS`와 회귀 테스트로 대조하는 유일한 core 제외 경로 목록이다.
경로는 `.lazyneon/` 기준이며 `<session>`·`<name>`·`*`는 비어 있지 않은 한 경로
요소, `<PID>`는 숫자다. 대소문자는 구분하지 않으며 심볼릭 링크를 해석한다.
아직 없는 파일의 나머지 경로도 유지한다.

<!-- core-owned-paths:start -->
- `pins.md`
- `ulw-scope.md`
- `ulw-dag.json`
- `lookups.jsonl`
- `feedback/<name>.jsonl`
- `feedback/<name>.jsonl.<PID>.taking`
- `logs/<name>.log`
- `logs/<name>.jsonl`
- `ulw-research/<session>/brief.md`
- `ulw-research/<session>/claim-graph.md`
- `ulw-research/<session>/intent-diff.md`
- `ulw-research/<session>/observation-manifest.md`
- `ulw-research/<session>/verification-economics.md`
- `ulw-research/<session>/cause-disappearance.md`
- `ulw-research/<session>/excursion-log.md`
- `ulw-research/<session>/expansion-log.md`
- `ulw-research/<session>/sources-ledger.md`
- `ulw-research/<session>/debate-log.md`
- `ulw-research/<session>/scope.md`
- `ulw-research/<session>/plan.md`
- `ulw-research/<session>/outcome.json`
- `ulw-research/<session>/verify-*.md`
<!-- core-owned-paths:end -->

고정 식별자·범위 잠금·DAG·조회 기록·피드백 큐·로그는 core 예약 상태다.
연구 세션의 작업 저널과 `verify-*.md` 검증 작업 기록만 제외한다.
최종 산출물 `report.md`, `report.html`, `SYNTHESIS.md`와 `sources/` 파일은
core 상태 면제를 받지 않으며 증거·환각·법률 가드의 일반 검사 경로로 전달한다.
내용별 적용 조건은 각 가드가 판단한다. `sources/`의 비보고서 원본을 근거 자료로
분류하는 것은 core 상태 면제와 별개의 내용 가드 규칙이다.

Workspace 자체 `pins.md`, `ulw-scope.md`, `audit_trail.jsonl`은
`.lazyneon-workspace/` 아래에서만 내부 상태로 다룬다.
`lookups/`, `feedback/`, `logs/` 전체나 `pins.md.backup`은 core 면제가 아니다.
이 계약은 작성 도구의 신원을 인증하지 않는다.
