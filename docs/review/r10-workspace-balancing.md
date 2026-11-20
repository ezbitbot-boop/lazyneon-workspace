# Round 10 WORKSPACE balancing 결과

대상은 workspace `2a0dc6c`. 두 최종 리뷰를 모두 읽고 코드와 대조했다. 아래 A는 `r10-astra-final.md`, C는 `r10-claude-final.md`의 항목이다. core 저장소는 변경하지 않았다.

| 항목 | 판정·변경 | 구현 위치 | 회귀 테스트 (`tests/test_r10_balancing.py`, 별도 표시 제외) |
| --- | --- | --- | --- |
| A1 | 수정: 모든 도구를 dispatcher에 전달, 실제 등록 경로로 검증 | `hooks.json:12`, `hooks.json:24` | `test_r10_real_hook_dispatch`, `test_r10_hooks_registered` |
| A2 | 수정: 복수 원본·공백·디렉터리 목적지, 명령별 옵션 해석 | `scripts/hook_targets.mjs:133` | `test_r10_directory_copy`, `test_r10_ffmpeg_option_roles` |
| A3 | 수정: 빈/잘못된 결과는 미확인, 명시적 PASS/WARN/FAIL/NOT_CHECKED/NOT_APPLICABLE 전달 | `scripts/guard_verdict.mjs:2`, `scripts/hook_targets.mjs:109`, `scripts/evidence_guard.mjs:698` | `test_r10_unknown_verdict`, `test_r10_lock_abort`; `tests/test_r7_workspace.py::test_unavailable_verifier_blocks_and_relays` |
| A4 | 수정: 잠금 획득 실패 시 append 중단, 시간만으로 타 프로세스 잠금 삭제 금지 | `scripts/evidence_guard.mjs:742` | `test_r10_lock_abort`, `test_r10_audit_concurrent` |
| A5 | 수정: 두 PII 진입점이 공통 패턴·정규화 사용, 국제 지역번호·신형 여권·라벨 번호 지원 | `scripts/pii_patterns.py:1`, `scripts/mask_korean_pii.py:112`, `scripts/pii_mask.py:45` | `test_r10_shared_pii` 및 기존 `test_pii_variants_mask_and_vault` |
| A6 | 수정: UTF-8/CP949 엄격 판별·동일 인코딩 저장, 읽기 오류 exit 2, 0건 출력도 갱신 | `scripts/pii_mask.py:98` | `test_r10_encoding_and_zero_output`, `test_r10_pii_read_error` |
| A7 | 수정: 별도 모델 다운로드 동의, offline 우선, 로컬 전용 로더와 정적 감사 등록 | `scripts/model_download_policy.py:7`, `scripts/local_ocr.py:103`, `scripts/local_stt.py:377`, `scripts/local_only_audit.py:48` | `test_r10_download_default`, `test_r10_download_consent_and_offline`, `test_r10_whisper_local_only`, `test_r10_other_models_offline_and_local` |
| A8 | 수정: 초기 쓰기 전 실제 경로 중첩 검사, 설정/기준선/로그 재사용 및 출력 링크 거부 | `scripts/case_mode.mjs:198` | `test_r10_case_overlap`, `test_r10_case_output_alias`, `test_r10_existing_settings`, `test_r10_case_existing_log_link` |
| A11 | 수정: 종료 코드·결과 스키마·독립 도구 목록 검증, matcher/CLI/래퍼 실패 주입 | `tests/test_r9_workspace.py:79`, `tests/test_r9_workspace.py:161`, `tests/test_r10_balancing.py:265` | `test_r10_symlink_cli_failure_detected`, `test_r10_matcher_mutation_detected`, `test_r10_windows_wrapper_contract` |
| C 높음-1 | 수정: 단일 증거는 파일/세그먼트만 보호, 작업 폴더 보고서 쓰기 허용 | `scripts/evidence_identity.mjs:33`, `scripts/case_mode.mjs:256` | `test_r10_single_evidence` |
| C 높음-2 | 수정: 입력이 아닌 쓰기 목적지만 신원 검사, 문서화 CLI 읽기 허용 | `scripts/evidence_guard.mjs:661`, `scripts/hook_targets.mjs:133` | `test_r10_read_semantics`, `test_r10_write_denied`, `test_r10_pii_directory_write_boundary` |
| C 높음-3 | 수정: 읽기 셸/MCP 무주입, 미확인 쓰기는 unchecked, -o/-t 의미 구분 | `scripts/domain_feedback.mjs:41`, `scripts/hook_targets.mjs:215` | `test_r10_read_relay`, `test_r10_mcp_read_relay`, `test_r10_unlisted_read_mcp`, `test_r10_unknown_script_policy` |
| C 높음-4 | 수정: 케이스 매니페스트를 실파일 해시와 대조하고 원본 경로도 전달; receipt·정상 체인 검증 유지 | `scripts/report_core.py:176`, `scripts/hallucination_guard.mjs:480` | `test_r10_manifest_grounding`, `test_r10_report_hook_manifest`; 기존 receipt/체인 변조 테스트 유지 |
| C 높음-5 | 수정: native realpath + NFC, 존재 조상 기준 새 경로 처리, Windows case folding, 증거 내 링크의 referent 보호 | `scripts/evidence_identity.mjs:6` | `test_r10_path_identity`, `test_r10_evidence_link_referent_protected` |
| C 중간-1 | 수정: exiftool 쓰기·tar directory·git work-tree·인터프리터 파일 쓰기 목적지 보호 | `scripts/hook_targets.mjs:133` | `test_r10_write_denied`, `test_r10_write_semantics_regressions`, `test_r10_interpreter_write_modes`, `test_r10_read_flags` |
| C 중간-2 | 수정: 하위 파일/디렉터리 링크를 초기화에서 거부; 링크 문자열만으로 내용 무결성 성공 주장 금지 | `scripts/case_mode.mjs:57`, `scripts/case_mode.mjs:106` | `test_r10_nested_symlink`; `tests/test_r4_workspace.py::test_case_links_recorded_without_following` |
| C 중간-3 | 수정: FILE·MDMP·KDMV에 구조 필드 검사 추가, 일반 FILE 텍스트 허용 | `scripts/evidence_identity.mjs:92` | `test_r10_file_header_text`, `test_r10_structural_signature` |
| C 중간-4 | 수정: claims --from은 입력, --session-dir은 출력으로 판정 | `scripts/hook_targets.mjs:150` | `test_r10_read_semantics`, `test_r10_write_denied`; 기존 `test_core_claim_gate_readonly_contract` |
| C 중간-6 | 수정: 기본 STT 예시는 로컬, 업로드는 이번 파일의 사용자 동의 조건으로 분리 | `skills/media-analysis/SKILL.md:33` | `test_r10_local_media_example` |
| C 중간-8 | 수정: case init·timestamp audit·문서 파서·exif 읽기 허용, audit -o 추가 | `scripts/hook_targets.mjs:16`, `skills/forensic-audit/scripts/audit_timestamps.py:136` | `test_r10_read_semantics`, `test_r10_read_tool_output_boundary`, `test_r10_timestamp_output` |
| C 낮음-1 | 수정: .lazyneon JSON·고정 evidence 루트 탐색 제거 | `scripts/evidence_identity.mjs:24` | `test_r10_no_core_registry_read` |
| C 낮음-2 | 수정: 세션 경로에 한정해 core 저널 제외, 규칙 문서 일치 | `scripts/hook_targets.mjs:25`, `docs/domain-targets.md:10`, `GEMINI.md:31` | `test_r10_core_journal`; 기존 사용자 brief/report 비면제 테스트 유지 |
| C 낮음-3 | 수정: 동의 테스트의 외부 offline 환경 격리; HWP 의존성 부재는 명시적 오류 계약 검증 | `tests/test_r8_workspace.py:80`, `tests/test_hwp5_fixture.py:114` | `test_youtube_offline_and_direct_consent`, `test_parse_hwp5_primary_or_fallback_no_error` |
| C 낮음-4 | 수정: 필수 Kiwi와 선택 모듈 분리, 필수 누락 exit 2 | `scripts/setup_forensic_env.py:89` | `test_r10_required_module` |
| C 낮음-5 | 수정: 세그먼트 표시 기준 dirname, 기본 이름에 현지 시간·오프셋 | `scripts/case_mode.mjs:194`, `scripts/case_mode.mjs:270` | `test_r10_case_display_and_settings` |
| C 낮음-6 | 수정: 비PDF 경로 명시, --skip-non-pdf를 선택한 경우만 보고 후 제외 | `scripts/bind_court_pdf.py:79`, `scripts/bind_court_pdf.py:120` | `test_r10_bind_mixed` |
| C 낮음-7 | 수정: patchText Add/Update/Delete/Move 본문 파싱 | `scripts/hook_targets.mjs:47` | `test_r10_patch_text`; 기존 모든 patch header 회귀 유지 |
| A9, C 높음-6 | 이번 repo 수정 반려(범위): 분류·게이트는 core `scripts/classify-task.mjs:266`, WORKSPACE에는 해당 구현 없음. 발견 자체를 오판으로 주장하지 않음 | 다른 저장소 | 실행/수정하지 않음 |
| A10 | 이번 repo 수정 반려(범위): 지적한 npm test·CI는 core `test/r8-security.test.mjs:55`, `test/r9-core.test.mjs:48`, `.github/workflows/core-tests.yml:5` | 다른 저장소 | Windows 네이티브 검증은 이 macOS 환경에서 미확인 |
| C 중간-5, 중간-7 | 이번 repo 수정 반려(범위): core write_chunk 및 markdown/json relay 소유 | core `scripts/write_chunk_guard.mjs:114`, `scripts/markdown_structure_guard.mjs:582`, `scripts/json_schema_guard.mjs:473` | 실행/수정하지 않음 |

## 수정 전 실패 확인

`git archive 2a0dc6c`로 `/tmp/lazyneon-r10-baseline`에 읽기 전용 Git 추출 사본을 만들고 새 테스트 파일을 복사해 실행했다. Git 쓰기 명령은 사용하지 않았다. 정상 허용/실제 우회 차단 대조군은 수정 전에도 일부 통과하는 것이 정상이다. 새 결함 회귀의 실패와 수정 후 통과를 확인했다. 테스트 자체의 강화는 잘못된 matcher, 깨진 CLI, 인자/종료 코드 전달을 제거한 래퍼 변형에서 assertion 실패를 확인했다.

C 낮음-3의 기존 두 테스트도 원래 사본에서 `LAZYNEON_OFFLINE=1`로 별도 실행해 실패를 확인했다. `r10-test-results` 아래 요약과 실행 tail에 정확한 결과를 보존한다.

## 기존 테스트 기대값 변경 이유

테스트 삭제·skip 추가·보안 우회 mocking은 하지 않았다. 다음 기존 기대값을 새 계약에 맞췄다.

- 빈 `{}` PASS/무검사 결과 → 명시적 PASS 또는 NOT_APPLICABLE. 검증 불능/크래시/없는 출력은 FAIL과 구분한 unchecked이며 제출 완료로 취급하지 않는다.
- matcher 문자열에 도구 이름이 들어 있는지 → 실제 정규식이 독립 도구 목록을 매칭하는지 검사한다.
- 외부 hashes.txt로 리다이렉트, 외부 evil.sh 삭제, 외부 copy.txt 출력, claims --from 읽기 → 허용. 증거 안 출력/삭제는 계속 차단한다.
- 링크 문자열만 비교한 case close 성공 → 링크 포함 init 거부와 원본 불변 확인. 링크 내용 미검증을 성공으로 부르지 않는다.
- setup --check 무조건 0 → 필수 Kiwi 설치 여부에 따른 0/2. HWP 파서 의존성이 모두 없으면 오류와 설치 안내를 확인하고, 설치 환경의 본문 추출 검증은 유지한다.
- golden snapshot은 검증 결과/경고 수가 아닌 HINT의 `audit.json` → `manifest.json` 한 문구만 변경했다.

## 검증 한계와 실행 제한

Windows 네이티브 래퍼 실행은 미확인이다. macOS에서는 래퍼 인자 전달·종료 코드·선택 인터프리터 소스 계약과 실패 변형을 검증했다. OCR/STT 모델 획득은 실제 네트워크 없이 로더 경계 스텁으로 검증했다. 보고서 훅 회귀는 Kiwi tokenizer만 스텁으로 대체하고 실제 해시·매니페스트·보고서 검증기를 실행했다.

agy / gemini / Antigravity / Google / gh / live doctor를 실행하지 않았다. 이름에 kakao가 든 테스트·스크립트는 실행하지 않았다. 기존 pytest 제외 설정과 5개 기존 skip을 유지했다. provenance/receipt/NOTICE 기록은 삭제하지 않았다.

## 실행 결과

- 수정 전 새 회귀: `94 failed, 24 passed, 5 warnings in 13.17s` (`2a0dc6c` 임시 추출 사본).
- 수정 전 offline 관련 기존 회귀: `2 failed in 0.09s`.
- 수정 후 새 회귀: `118 passed, 5 warnings in 11.83s`.
- Node 계약: 6 tests / 6 pass / 0 fail.
- 전체 실행 명령: `LAZYNEON_OFFLINE=1 LAZYNEON_WS_PYTHON=/opt/homebrew/bin/python3.12 python3.12 -m pytest tests test -q`.
- 원래 시스템 `python3`에는 pytest가 없어 Python 3.12를 사용했다. 패키지 설치나 네트워크 다운로드는 하지 않았다.

최종 전체 실행 tail (원문):

```text
........................................................................ [ 93%]
........................................................................ [ 99%]
............                               [100%]
1227 passed, 5 skipped, 17 deselected, 1114 subtests passed in 119.70s (0:01:59)
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

`git diff --check`도 통과했다. 커밋은 생성하지 않았다.
