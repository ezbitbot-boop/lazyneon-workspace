# Round 11 Workspace 수정 기록

기준: `a28c647059c24634ab8440b7b2dbbd0f67f81c03`. 지정 리뷰 문서 전체와 현재 구현을 대조했다. Workspace 지적 중 잘못된 것으로 기각한 항목은 없다. 아래 core 소유 항목은 이 저장소의 수정 범위에서 제외했다.

| 지적 | 결과와 구현 | 회귀 테스트 (`tests/test_r11_workspace.py`) |
|---|---|---|
| 치명-1, r10 중간-1 PARTIAL | 수정. `scripts/evidence_protection.py:23` OS 쓰기 보호; `scripts/case_mode.mjs:235` 적용 기록; `scripts/evidence_manifest.py:129` manifest CLI 보호; `scripts/evidence_read_policy.mjs:40` 증거 참조 명령의 프로그램·플래그 허용표 | `test_r11_os_protection_and_unlock`, `test_r11_manifest_protection`, `test_r11_real_hook_allowlist`, `test_r11_command_aliases_and_parent_workspace`, `test_r11_read_program_write_flags_denied` |
| 높음-1 | 수정. `scripts/local_stt.py:575`, `scripts/local_ocr.py:207`, `scripts/evidence_output.py:34` 작업 폴더 기본 출력과 증거 내부 출력 거부. whisper 바이너리 중간 파일도 작업 폴더 임시 디렉터리 사용 | `test_r11_stt_default_and_output_refusal`, `test_r11_ocr_scan_export_output_refusal`, `test_r11_whisper_binary_scratch`, `test_r11_output_from_parent_workspace` |
| 중간-1 | 수정. `scripts/hallucination_guard.mjs:684`, `scripts/guard_verdict.mjs:7` 형태소 엔진 부재보다 확정 FAIL 우선 | `test_r11_morph_failure_priority` |
| 중간-3 | 수정. `scripts/generated_artifact.py:4`, `scripts/hallucination_guard.mjs:620` 명시적 non-report 헤더와 본문 해시. 본문 변경은 FAIL, 파일명은 면제 근거가 아님 | `test_r11_generated_artifact_and_tamper`, `test_r11_real_scan_and_sheet` |
| 낮음-1 | 수정. `scripts/hook_targets.mjs:110` 디렉터리 제외, `:181` BSD sed 표현식 제외, `:87` git rm 삭제로 분류 | `test_r11_quiet_targets` |
| 낮음-2 | 수정. `scripts/case_mode.mjs:322` close에서 링크를 CHANGED로 수집하고 다른 변경·삭제와 close 로그까지 기록 | `test_r11_close_symlink_continues` |
| 낮음-3 | 수정. `scripts/evidence_guard.mjs:752` PID·호스트 기록, 죽은 소유자/5분 초과 소유자 불명 잠금 복구 및 감사 note. 살아 있는 PID는 오래되어도 회수하지 않음 | `test_r11_stale_and_live_lock`, `test_r11_dead_pid_lock`; 기존 `test_r10_audit_concurrent` |
| 낮음-4 | 수정. `scripts/pii_patterns.py:43` 괄호 지역번호 공통 탐지 | `test_r11_bracket_phone`, `test_r11_pii_entrypoints` |
| 기존 잔여: 상위 사건 폴더 workspace | 수정. `scripts/evidence_identity.mjs:24` 바로 아래 케이스의 custody 위치도 탐색. core `.lazyneon`은 탐색하지 않음 | `test_r11_command_aliases_and_parent_workspace` |
| 기존 잔여: MCP move source | 수정. `scripts/hook_targets.mjs:76` source를 move-src로 수집 | `test_r11_command_aliases_and_parent_workspace` |
| 중간-2, r10 높음-6·A9 PARTIAL (`/ulw`) | 범위 제외. 이 저장소에 classify-task.mjs, session-model.mjs, model-routing.json이 없다. `scripts/session_start.mjs:14`도 모델 라우팅을 core 소유로 명시한다. core 저장소를 수정하지 않았다 | 해당 없음; 이 저장소에서 수정/통과했다고 주장하지 않음 |
| A10 PARTIAL Windows 첫 검증 | 범위 제외/미확인. 리뷰의 npm test:first와 CI 매트릭스는 core 소유. macOS 호스트에서 Windows 실행 결과를 확인할 수 없음 | Windows 실제 실행 미확인 |

OS 보호는 macOS에서 실제 실행했다. Linux는 chmod와 비루트 chattr 시도/불가 note, Windows는 attrib와 현재 사용자 deny-write ACL 구현을 추가했으나 해당 OS 실검증은 미확인이다. 기존 Windows ACL은 manifest에 보존하여 unlock 때 복원한다. `case-mode unlock --case … --reason …` 또는 `--manifest … --reason …`은 요청/완료 로그를 남긴다. close/verify는 자동 해제하지 않는다.

OS 공격 테스트는 테스트가 만든 임시 트리에서 perl, bash rm, find -delete, ln -sf, Node copyFileSync, Python open(w), tar 추출, cp/mv/rm/tee/dd/redirect를 실제 실행하고 매번 SHA-256 불변을 확인했다. macOS perl과 find는 OS 거부 진단을 출력하면서 종료 코드 0을 반환하므로 해당 진단과 해시를 함께 검사한다. 모든 보호 테스트는 finally/fixture finalizer에서 nouchg와 권한 복원을 수행한다.

`git rm`, `git checkout` 실제 실행은 사용자의 git 쓰기 금지 조건에 따라 하지 않았다. git을 포함한 43개 명령 형태는 실제 hooks.json 경유 차단/작업 폴더 허용을 검증했다. NFC/NFD/대소문자/심볼릭 링크 변형도 검사했다. 외부 에이전트, Google, Antigravity probe, gh, 네트워크 설치, 이름에 kakao가 포함된 테스트/스크립트를 실행하지 않았다. provenance/receipt/NOTICE 기록을 삭제하지 않았다.

기존 테스트 변경은 계약 변경을 반영한다.

- `test_r10_read_flags`: 증거를 참조하는 임의 인라인 Python은 새 명시적 허용표에서 거부한다. exiftool 읽기와 조용한 relay 검증은 유지했다.
- `test_pipeline_with_external_delete_allowed`: 증거 읽기와 삭제가 섞인 복합 셸은 허용표 밖이므로 거부 기대값으로 변경했다.
- `test_slop_crash_is_not_pass`: 디렉터리는 검사 대상이 아니므로 실제 읽기 불가 보고서로 검증기 실패를 재현했다. 기존 unchecked/주입 단정은 유지했다.
- 기존 case tamper/rename 테스트: init의 OS 잠금으로 쓰기가 실패하므로 명시적 사유를 남기는 unlock 이후 원래 변경 탐지 단정을 수행한다.
- 테스트용 임시 트리만 대상으로 finally 정리를 추가했다. 테스트를 삭제·축소·skip하지 않았다.

수정 전 검증은 git archive HEAD의 읽기 전용 출력으로 만든 별도 임시 기준본에 최신 회귀 테스트를 복사하여 실행했다. 최종 새 회귀 126건: **수정 전 117 failed, 9 passed**. 수정 후 새 회귀 126건 전부 통과, 관련 전체 검사 **608 passed, 5 warnings in 84.80s (0:01:24)**. 경고는 PyMuPDF/SWIG의 DeprecationWarning이다. 실행 명령과 원문 tail은 `r11-validation-tail.txt`에 기록했다. `git diff --check`도 통과했다.
