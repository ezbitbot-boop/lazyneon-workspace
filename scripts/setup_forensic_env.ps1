<#
.SYNOPSIS
    Python 3.12+ 공통 설치기로 선택 의존성과 requirements.txt를 설치한다.
.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup_forensic_env.ps1 -Check
#>
param(
    [switch]$Check,
    [string]$Dir = "$env:USERPROFILE\.lazyneon-workspace/venv",
    [string[]]$With = @()
)
$ErrorActionPreference = "Stop"
$python = $env:LAZYNEON_WS_PYTHON
if (-not $python) { $python = $env:LAZYNEON_WS_LEGACY_PYTHON }
if (-not $python) {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if (-not $command) { $command = Get-Command py -ErrorAction SilentlyContinue }
    if ($command) { $python = $command.Source }
}
if (-not $python) {
    Write-Error "python을 찾을 수 없습니다. python.org에서 3.12+ 설치 후 재시도하세요."
    exit 2
}
$forward = @("--dir", $Dir)
if ($Check) { $forward += "--check" }
if ($With.Count -gt 0) { $forward += "--with"; $forward += $With }
& $python (Join-Path $PSScriptRoot "setup_forensic_env.py") @forward
exit $LASTEXITCODE
