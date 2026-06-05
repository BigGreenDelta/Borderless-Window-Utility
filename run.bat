@echo off
start "Borderless Window Utility" /d "%~dp0" powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$path = '%~f0'; $lines = Get-Content $path; $marker = [Array]::IndexOf($lines, ':: POWERSHELL'); if ($marker -lt 0) { throw 'Missing PowerShell marker.' }; $script = ($lines[($marker + 1)..($lines.Length - 1)] -join [Environment]::NewLine); & ([scriptblock]::Create($script)) '%~dp0'"
goto :eof
:: POWERSHELL
param([string]$RepoRoot)

Set-Location $RepoRoot
& uv run python main.py

if ($null -ne $LASTEXITCODE) {
    $exitCode = [int]$LASTEXITCODE
}
elseif ($?) {
    $exitCode = 0
}
else {
    $exitCode = 1
}

if ($exitCode -ne 0) {
    Write-Host
    Write-Host ('Command failed with exit code {0}.' -f $exitCode)
    Read-Host 'Press Enter to continue' | Out-Null
}

exit $exitCode
