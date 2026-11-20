# lazyothers.ps1 — bin/lazyothers의 Windows 네이티브 판 (PowerShell)
# 사용: PATH에 이 bin\ 디렉터리를 추가하면 cmd/PowerShell 어디서든:
#   lazyothers doc <파일>           (cmd shim: lazyothers.cmd 경유)
#   powershell -File bin\lazyothers.ps1 doc <파일>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)

# 우선순위: $LAZYNEON_WS_PYTHON > $LAZYNEON_WS_LEGACY_PYTHON > $Root\.venv > %USERPROFILE%\.lazyneon-workspace/venv > python > py
if ($env:LAZYNEON_WS_PYTHON) {
    $Py = $env:LAZYNEON_WS_PYTHON
} elseif ($env:LAZYNEON_WS_LEGACY_PYTHON) {
    $Py = $env:LAZYNEON_WS_LEGACY_PYTHON
} elseif (Test-Path "$Root\.venv\Scripts\python.exe") {
    $Py = "$Root\.venv\Scripts\python.exe"
} elseif (Test-Path "$env:USERPROFILE\.lazyneon-workspace/venv\Scripts\python.exe") {
    $Py = "$env:USERPROFILE\.lazyneon-workspace/venv\Scripts\python.exe"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Py = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $Py = "py"
} else {
    Write-Error "python을 찾을 수 없습니다. python.org에서 3.12+ 설치 후 재시도하세요."
    exit 2
}

& $Py @args
exit $LASTEXITCODE
