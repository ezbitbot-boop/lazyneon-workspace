# Shared executable/version probe for Windows PowerShell 5.1 and PowerShell 7.
function Test-WorkspacePython($Executable, [string[]]$Prefix) {
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo.FileName = $Executable
    $process.StartInfo.Arguments = (($Prefix + @('-c', '"import sys; print(312 if sys.version_info >= (3, 12) else 0)"')) -join ' ')
    $process.StartInfo.UseShellExecute = $false
    $process.StartInfo.CreateNoWindow = $true
    $process.StartInfo.RedirectStandardOutput = $true
    $process.StartInfo.RedirectStandardError = $true
    try {
        if (-not $process.Start()) { return $false }
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(3000)) { $process.Kill(); return $false }
        # A launcher/Store alias exiting zero is not proof that Python ran.
        if (-not $stdout.Wait(200)) { return $false }
        return ($process.ExitCode -eq 0 -and $stdout.Result.Trim() -eq "312")
    } catch { return $false } finally { $process.Dispose() }
}
function Select-WorkspacePython([string]$Root) {
    $custom = $env:LAZYNEON_WS_PYTHON
    if (-not $custom) { $custom = $env:LAZYNEON_WS_LEGACY_PYTHON }
    if ($custom) {
        if (-not (Test-WorkspacePython $custom @())) { throw "Configured Python is not executable Python 3.12+: $custom" }
        return @{Executable=$custom; Arguments=@()}
    }
    $candidates = @(
        @{Executable=(Join-Path $Root '.venv/Scripts/python.exe'); Arguments=@()},
        @{Executable=(Join-Path $env:USERPROFILE '.lazyneon-workspace/venv/Scripts/python.exe'); Arguments=@()},
        @{Executable='python'; Arguments=@()},
        @{Executable='py'; Arguments=@('-3.12')}
    )
    foreach ($candidate in $candidates) {
        if (Test-WorkspacePython $candidate.Executable $candidate.Arguments) { return $candidate }
    }
    throw 'No executable Python 3.12+ found. Install Python or set LAZYNEON_WS_PYTHON.'
}
