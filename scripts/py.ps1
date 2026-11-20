# lazyothers.ps1 — bin/lazyothers의 Windows 네이티브 판 (PowerShell)
# 사용: PATH에 이 bin\ 디렉터리를 추가하면 cmd/PowerShell 어디서든:
#   lazyothers doc <파일>           (cmd shim: lazyothers.cmd 경유)
#   powershell -File bin\lazyothers.ps1 doc <파일>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)

. (Join-Path $Root "scripts/select_python.ps1")
$selection = Select-WorkspacePython $Root
$Py = $selection.Executable
$PyArgs = @($selection.Arguments)

& $Py @PyArgs @args
exit $LASTEXITCODE
