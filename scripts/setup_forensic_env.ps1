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
. (Join-Path $PSScriptRoot "select_python.ps1")
$selection = Select-WorkspacePython (Split-Path -Parent $PSScriptRoot)
$python = $selection.Executable
$PyArgs = @($selection.Arguments)
$forward = @("--dir", $Dir)
if ($Check) { $forward += "--check" }
if ($With.Count -gt 0) { $forward += "--with"; $forward += $With }
& $python @PyArgs (Join-Path $PSScriptRoot "setup_forensic_env.py") @forward
exit $LASTEXITCODE
