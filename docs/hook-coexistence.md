# Core와 Workspace 훅 공존

권장 설치 순서는 core, Workspace다. 각 명령의 cwd는 해당 플러그인 루트이며,
작업 폴더는 이벤트의 workspacePaths/cwd로 전달한다. 호스트가 플러그인 간 순서를
보장한다는 뜻은 아니다. 아래는 합성 이벤트 테스트의 실행 순서이며 역순도 검사한다.

| 이벤트 | Core | Workspace | 결합 계약 |
| --- | --- | --- | --- |
| SessionStart | 일반 규칙·라우팅·companion | 도메인 규칙·core 상태 | 각 injectSteps를 누적, 상태 소유권 분리 |
| PreToolUse | write_chunk_guard | evidence_guard pre-tool-use | 어느 하나라도 deny면 실행 금지, 빈 응답은 허용 결정이 아님 |
| PostToolUse | post_tool_feedback batch (markdown/json 및 matcher 해당 시 lookup) | domain_feedback batch (4개 도메인 가드) | 둘 다 {} 반환, 각자 큐에 결과 보존 |
| PreInvocation | post_tool_feedback inject, usage_guard | domain_feedback inject | 인용된 ephemeralMessage를 누적, 서로 덮어쓰지 않음 |
| Stop | stop_claim_guard, reply_format_guard | 없음 | core의 종료 계약 유지 |

core는 `.lazyneon/`, Workspace는 `.lazyneon-workspace/`를 소유한다.
두 플러그인의 사용자 피드백 큐도 각각 `~/.lazyneon/feedback`, `~/.lazyneon-workspace/feedback`이다.
사후 FAIL은 원본 복원이 아니며 수정·재검증 전 제출 금지다.
판정 게이트의 입력 자료 주입 검사는 core /ulw의 injection pre-filter 단계에서 수행한다.
Workspace는 core 코드를 import하지 않으며 미설치 시 이 단계가 보장되지 않음을 경고한다.

`tests/test_hook_coexistence.py`는 형제 core의 실제 hooks.json을 읽고 등록 명령을
실행하는 r6 방식의 프로세스 시뮬레이터다. 안전한 읽기와 증거 쓰기 거부,
각 이벤트의 JSON 계약을 두 순서로 확인한다.
실제 core write_chunk_guard는 작은 증거 쓰기에 allow를, Workspace는 deny를 반환한다.
원시 결정의 일치는 입증되지 않았으며, 시뮬레이터는 deny 우선 결합 계약을 검증한다.
호스트가 마지막 응답 우선으로 처리한다면 안전하지 않다. 실제 호스트의 deny 우선 적용은 미검증이다. core가 없는 단독 배포에서는
이 통합 테스트만 이유를 명시해 건너뛴다. 실제 Antigravity 이벤트 전달·UI는 미검증이다.
