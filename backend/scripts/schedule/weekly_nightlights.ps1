param(
    [string]$BackendRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path,
    [string]$PythonExe = (Join-Path $env:LOCALAPPDATA "Python/bin/python.exe")
)

$ErrorActionPreference = "Stop"
Set-Location $BackendRoot
if (-not (Test-Path -LiteralPath $PythonExe)) {
    $PythonExe = (Get-Command python -ErrorAction Stop).Source
}
$logDir = Join-Path $BackendRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$date = Get-Date -Format "yyyy-MM-dd"
$logPath = Join-Path $logDir "nightlights_$date.log"
Start-Transcript -Path $logPath -Append
try {
    & $PythonExe scripts/ingest/fetch_nightlights.py
    if ($LASTEXITCODE -ne 0) { throw "NASA nightlights ingest failed with exit code $LASTEXITCODE" }
    & $PythonExe scripts/process/build_cells_nightlights.py
    if ($LASTEXITCODE -ne 0) { throw "Nightlights processing failed with exit code $LASTEXITCODE" }
} catch {
    Write-Error $_
    Stop-Transcript
    exit 1
}
Stop-Transcript

# Register from an elevated PowerShell prompt; update the user and backend path as needed:
# schtasks /create /tn "OSEAS Weekly Nightlights" /sc weekly /d SUN /st 02:00 /tr "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"D:\path\to\backend\scripts\schedule\weekly_nightlights.ps1\"" /f
