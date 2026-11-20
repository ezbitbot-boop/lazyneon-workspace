$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
& node (Join-Path $Root "scripts\case_mode.mjs") @args
exit $LASTEXITCODE
