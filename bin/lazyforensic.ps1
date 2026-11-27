# lazyforensic.ps1 — bin/lazyforensic의 Windows 네이티브 판 (PowerShell)
# 사용: PATH에 이 bin\ 디렉터리를 추가하면 cmd/PowerShell 어디서든:
#   lazyforensic scan <폴더>        (cmd shim: lazyforensic.cmd 경유)
#   powershell -File bin\lazyforensic.ps1 scan <폴더>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)

. (Join-Path $Root "scripts/select_python.ps1")
$selection = Select-WorkspacePython $Root
$Py = $selection.Executable
$PyArgs = @($selection.Arguments)

function Usage {
    Write-Host @"
lazyforensic - 증거 선조사 CLI 래퍼 (외부 STT는 --upload-audio 동의 필요, Windows)

  lazyforensic scan <폴더> [--keywords ...] [--stt] [--upload-audio] [-o out.json] [--markdown out.md]
  lazyforensic stt <오디오|폴더> [--keywords ...] [--verbatim]
  lazyforensic pii <파일|폴더> [--mask]
  lazyforensic manifest <폴더> [-o m.json] [--verify m.json]
  lazyforensic sig <파일|폴더>        매직바이트 위장 감사
  lazyforensic dedup <폴더>           중복 파일 탐지
  lazyforensic similar <폴더>         유사 이미지 검색 (Pillow)
  lazyforensic exif <파일|폴더>       이미지 메타데이터 감사 (Pillow)
  lazyforensic kw <폴더> "키워드"     증거형 키워드 리포트
  lazyforensic archive <파일|폴더>    zip/tar 내부 감사
  lazyforensic pdf <파일|폴더>        PDF 구조 감사
  lazyforensic db <파일|폴더>         SQLite 표면 조사 (읽기전용)
  lazyforensic vcheck <파일|폴더>     영상 손상 감지 (ffmpeg)
  lazyforensic vfp <영상> [--compare B]  영상 지문 (ffmpeg)
  lazyforensic afp <폴더>             오디오 지문 유사 쌍 (fpcalc)
  lazyforensic osint <닉네임>         sherlock OSINT (외부 쿼리 — 동의 필요)
  lazyforensic timeline --manifest m.json ...   다중 소스 시각 병합
  lazyforensic cite <보고서.md> --evidence <폴더>  보고서 인용 값(해시·일시·인용문·수치) 증거 대조
  lazyforensic sheet <manifest.json> [--party 갑] 서증 목록표 초안
  lazyforensic export <manifest.json> -o e.json   lazyothers evidence.json 변환
  lazyforensic dlp <로그.csv>          DLP 로그 -> 체크리스트 표 (탐지 아님, 정리)
  lazyforensic audit                  외부 반출 경로 정적 감사
  lazyforensic setup [-Check]         선택 의존성 환경 설치/진단
"@
}

if ($args.Count -lt 1) { Usage; exit 2 }
$cmd = $args[0]
$rest = @($args | Select-Object -Skip 1)

switch ($cmd) {
    "triage" { & $Py @PyArgs (Join-Path $Root "scripts/case_survey.py") @rest; exit $LASTEXITCODE }
    "kakao" { & $Py @PyArgs (Join-Path $Root "skills/kakao-chat-extractor/scripts/parse_kakao.py") @rest; exit $LASTEXITCODE }
    "telegram" { & $Py @PyArgs (Join-Path $Root "skills/telegram-chat-extractor/scripts/parse_telegram.py") @rest; exit $LASTEXITCODE }
    "mft" { & $Py @PyArgs (Join-Path $Root "scripts/parse_ntfs_artifacts.py") @rest; exit $LASTEXITCODE }
    "video" { & $Py @PyArgs (Join-Path $Root "skills/forensic-video/scripts/forensic_video_audit.py") @rest; exit $LASTEXITCODE }
    "deepfake" { & $Py @PyArgs (Join-Path $Root "scripts/analyze_deepfake_evidence.py") @rest; exit $LASTEXITCODE }
    "timestamps" { & $Py @PyArgs (Join-Path $Root "skills/forensic-audit/scripts/audit_timestamps.py") @rest; exit $LASTEXITCODE }
    "verify" { & $Py @PyArgs (Join-Path $Root "scripts/verify_report.py") @rest; exit $LASTEXITCODE }
    "cite" { & $Py @PyArgs (Join-Path $Root "scripts/citation_grounding.py") @rest; exit $LASTEXITCODE }
    "evtx" { if ($rest.Count -eq 0) { $rest = @("hayabusa.exe", "chainsaw.exe") }; & $Py @PyArgs (Join-Path $Root "scripts/check_tool.py") @rest; exit $LASTEXITCODE }
    "memory" { if ($rest.Count -eq 0) { $rest = @("MemProcFS.exe", "vol.py") }; & $Py @PyArgs (Join-Path $Root "scripts/check_tool.py") @rest; exit $LASTEXITCODE }

    "scan"     { $script = "case_survey.py" }
    "stt"      { $script = "local_stt.py" }
    "pii"      { $script = "pii_mask.py" }
    "manifest" { $script = "evidence_manifest.py" }
    "sig"      { $script = "signature_check.py" }
    "dedup"    { $script = "dedup_files.py" }
    "similar"  { $script = "image_similarity.py" }
    "exif"     { $script = "exif_audit.py" }
    "kw"       { $script = "keyword_report.py" }
    "archive"  { $script = "archive_survey.py" }
    "pdf"      { $script = "pdf_audit.py" }
    "db"       { $script = "sqlite_survey.py" }
    "vcheck"   { $script = "video_integrity.py" }
    "vfp"      { $script = "video_fingerprint.py" }
    "afp"      { $script = "audio_fingerprint.py" }
    "osint"    { $script = "osint_username.py" }
    "timeline" { $script = "merge_timeline.py" }
    "sheet"    { $script = "court_evidence_sheet.py" }
    "export"   { $script = "evidence_export.py" }
    "dlp"      { $script = "dlp_log_table.py" }
    "audit"    { $script = "local_only_audit.py" }
    "setup" {
        & powershell -NoProfile -ExecutionPolicy Bypass -File `
            (Join-Path $Root "scripts\setup_forensic_env.ps1") @rest
        exit $LASTEXITCODE
    }
    { $_ -in @("-h", "--help", "help") } { Usage; exit 0 }
    default { Write-Error "알 수 없는 명령: $cmd"; Usage; exit 2 }
}

& $Py @PyArgs (Join-Path $Root "scripts\$script") @rest
exit $LASTEXITCODE
