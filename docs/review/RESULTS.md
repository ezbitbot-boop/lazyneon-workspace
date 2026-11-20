# LazyNeon Workspace 0.1.0 변경 검토

구현·오프라인 검증과 실연동을 구분한다. 배포 또는 실연동 성공 선언이 아니다.

## 스킬 상태

| 스킬 | 승인 분류 | 결과·제한 |
| --- | --- | --- |
| court-evidence-stamper | KEEP | 도메인 기능 유지 |
| court-pdf-binder | KEEP | 도메인 기능 유지 |
| evidence-integrity-audit | KEEP | 도메인 기능 유지 |
| financial-flow-tracer | KEEP | 도메인 기능 유지 |
| korean-pii-masker | KEEP | 도메인 기능 유지 |
| case-mode | KEEP-AFTER-FIX | 호스트 실행 제거; 자체 상태·미적용 보호 정책 명시. 해시 검출 통과. |
| court-ruling-analyzer | KEEP-AFTER-FIX | JSON→TXT 연결 수정; 원문 조회 선택화. |
| deepfake-forensic-radar | KEEP-AFTER-FIX | 바이트 표식과 암호학적 서명 검증 구분. |
| forensic-audit | KEEP-AFTER-FIX | 호스트 전제 제거; 원격 수집 선택화·미검증 명시. |
| forensic-report | KEEP-AFTER-FIX | 외부 디자인 문서 참조 제거, 자체 절차 유지. |
| forensic-timeline | KEEP-AFTER-FIX | 모델·위임 계약을 코어에 위임. |
| forensic-video | KEEP-AFTER-FIX | 업로드 기본 꺼짐; 실제 프레임 추출 통과. 서버 STT 미검증. |
| humanize-korean | KEEP-AFTER-FIX | 모델 전제 제거; 복원·게이트 회귀 통과. Neon 품질 미검증. |
| kakao-chat-extractor | KEEP-AFTER-FIX | 호스트 지침 수정. 금지 규칙상 파서 실행 미실시. |
| korean-doc-parser | KEEP-AFTER-FIX | olefile 미설치 재현. 의존성 명시·기존 테스트 유지. 설치 필요. |
| lazyforensic | KEEP-AFTER-FIX | DROP 링크 제거; STT·OSINT·설치의 외부 통신 명시. |
| legal-draft-builder | KEEP-AFTER-FIX | 65% 유지; 정확한 서증 메타 행만 분리. 사실 본문 새 용어는 실패. |
| media-analysis | KEEP-AFTER-FIX | 모델 경험칙 제거; 업로드 동의 정책 통일. 서버 품질 미검증. |
| report-guard | KEEP-AFTER-FIX | 상태 분리; 사후 검증 한계와 제출 금지 정책 명시. |
| sqlite-evidence-query | KEEP-AFTER-FIX | 고정 식별자를 자체 상태 경로에 저장. |
| telegram-chat-extractor | KEEP-AFTER-FIX | 호스트 지침 수정; 파싱·타임라인 코드 유지. |
| video-editor | 비활성/실험 | experimental/로 이동, 자동 발견·라우팅 제외 |
| web-evidence-capture | 비활성/실험 | experimental/로 이동, 자동 발견·라우팅 제외 |
| ai-trace-detector | DROP | 폴더·라우팅 삭제 |
| dfir-evtx-hunter | DROP | 폴더·라우팅 삭제 |
| dlp-leakage-detector | DROP | 폴더·라우팅 삭제 |
| forensic-mft-parser | DROP | 폴더·라우팅 삭제 |
| infographic-creator | DROP | 폴더·라우팅 삭제 |
| legal-case-search | DROP | 폴더·라우팅 삭제 |
| legal-forensic-consult | DROP | 폴더·라우팅 삭제 |
| memory-triage | DROP | 폴더·라우팅 삭제 |

## 삭제 사유와 보존

- [전체 삭제 파일](deleted-files.json): DROP 전용 코드·규칙, 미사용 원장/봉투/통합 파이프라인/MCP 생성기, 법률 MCP 설치·래퍼, DFIR 다운로더, 미사용 Windows 잠금기, 평가·테스트 실행기·법령 갱신 보조, 기존 호스트 설치·동기화·탐지, 코어 소유 일반 가드를 제거했다.
- [삭제 전 참조 검색](deletion-reference-audit.json): 런타임 호출과 테스트·문서 언급을 구분할 수 있도록 원본 검색 기록을 보존했다. 제거된 자동 업데이트·감지·일반 가드 사이의 참조도 함께 제거했다.
- `setup_forensic_env.ps1`은 유지 Windows CLI가 실제 호출하므로 보존했다. `parse_ntfs_artifacts.py`, `check_tool.py`도 유지 라우터가 사용한다.
- 두 CLI는 유지 도메인 기능을 호출한다. 법률 초안 스킬에 문서 CLI 단축 명령을 명시했다.
- [삭제 테스트 사례](deleted-test-cases.json)는 제거된 기능 전용이다. 혼합 파일의 유지 기능 검증은 보존했다. 경로·버전·모델 위임·카탈로그 기대값은 새 계약으로 갱신했다.
- 기존 NOTICE 본문, 계약 PIN, 수신증·출처 기록은 보존했다. 과거 실호스트 검증 기록을 이 버전의 성공 근거로 사용하지 않는다.

## 두 실패의 원인

법률 초안의 입증방법 행은 `method_line()`이 서증 목록에서 생성한다. 호증·문서유형까지 사실 문장으로 평가하면서 60%로 떨어졌다. 문서명을 전역 면제하지 않고 정확한 메타 행 형식과 제한된 문서유형에만 예외를 적용했다. 65% 기준은 유지했고, 사실 본문에 새로운 전문용어를 넣으면 실패하는 회귀 테스트를 추가했다.

HWP5 재현 출력은 `No module named 'olefile'`이다. 기존 오류 메시지가 설치할 패키지를 명시한다. requirements의 `olefile>=0.47,<1`을 HWP 기능 필수 의존성으로 유지했다. 테스트의 의도는 정상 텍스트 추출이므로 실패를 정상으로 바꾸거나 skip을 추가하지 않았다. 실행 Python에 olefile 설치 후 재검증해야 한다.

## 검증 제한

기본 `/usr/bin/python3`에는 pytest가 없어 `No module named pytest`로 종료했다. 실제 검증은 PATH 앞에 `/opt/homebrew/opt/python@3.12/libexec/bin`을 추가해 Python 3.12.12 / pytest 9.1.1로 수행했다.

요청한 파일명 제외 명령만으로는 금지 규칙을 지킬 수 없다. `test_forensic_scripts.py`는 수집 시 금지 파서를 import한다. `test_review_regressions.py`의 CLI 도움말 테스트와 `test_phase2_d_drive_regressions.py`의 디렉터리 파서 테스트도 내부 실행한다. 요청 명령 그대로의 전체 합계는 제공할 수 없다. 파일과 테스트는 보존했고, 뒤 두 파일은 금지 호출 사례만 선택 해제한 별도 실행으로 안전한 사례를 검증했다.

금지된 호스트 CLI, Google 네트워크 호출, git 쓰기 명령 및 gh는 실행하지 않았다. 새 영상 테스트는 합성 영상을 FFmpeg로 만들고 실제 프레임을 추출한다. 기존 mock 테스트를 실서버 성공 근거로 계산하지 않는다.

남은 이전 제품명 검색 결과는 삭제 목록과 삭제 전 원본 참조 기록 7줄에만 있으며 런타임 결합이 아니다.

## 정확한 실행 명령과 출력 꼬리

기본 Python의 최초 재현 시도: `/Library/Developer/CommandLineTools/usr/bin/python3: No module named pytest`.

주 검증 명령 (금지 내부 호출이 포함된 세 파일 제외):

```sh
PATH=/opt/homebrew/opt/python@3.12/libexec/bin:$PATH python3 -m pytest -q -p no:cacheprovider $(ls test/*.py tests/*.py | grep -v -i kakao | grep -v -E 'test_forensic_scripts.py|test_review_regressions.py|test_phase2_d_drive_regressions.py')
```

[주 검증 원문](python-final.txt)의 출력 꼬리:

```text
1 failed, 747 passed, 8 skipped, 1114 subtests passed in 44.51s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

실패는 HWP5 olefile 미설치 1건이다. 기존 skip을 추가하거나 늘리지 않았다.

안전한 혼합 파일 사례:

```sh
PATH=/opt/homebrew/opt/python@3.12/libexec/bin:$PATH python3 -m pytest -q -p no:cacheprovider test/test_review_regressions.py tests/test_phase2_d_drive_regressions.py -k 'not test_cli_subcommands_help and not test_parse_kakao_directory_mode'
```

[출력](python-safe-mixed.txt):

```text
25 passed, 2 deselected in 0.58s
```

`node --test test/*.test.mjs`의 [출력](node-final.txt):

```text
ℹ tests 5
ℹ suites 0
ℹ pass 5
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 303.683375
```

기존 Node 10개는 제거된 자동 업데이트 전용 테스트였다. 새 5개는 선택 컨텍스트 무변경 읽기·상태 미생성·도메인 가드 등록·승인 카탈로그·실제 해시 변조 검출을 검증한다. 기존 유지 코드 테스트를 축소해 만든 개수가 아니다.
