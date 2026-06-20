param(
    [string]$ApiBase = "http://127.0.0.1:8750",
    [int]$DurationSec = 14400,
    [int]$IntervalSec = 30,
    [string]$ReportPath = ""
)

$ErrorActionPreference = "Stop"

$scriptRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($PSScriptRoot)
$repoRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath((Join-Path $scriptRoot ".."))
$backendDir = Join-Path $repoRoot "backend"
$pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Backend virtualenv not found at $pythonExe"
}

if (-not $ReportPath) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $reportsDir = Join-Path $repoRoot "reports"
    New-Item -ItemType Directory -Force -Path $reportsDir | Out-Null
    $ReportPath = Join-Path $reportsDir "installed-soak-$stamp.json"
}

Push-Location $backendDir
try {
    $output = & $pythonExe .\tools\run_smoke_matrix.py `
        --api $ApiBase `
        --mode soak `
        --duration-sec $DurationSec `
        --interval-sec $IntervalSec
    if ($LASTEXITCODE -ne 0) {
        throw "Installed soak matrix failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

$output | Set-Content -Path $ReportPath -Encoding UTF8
Write-Host "Installed soak report written to $ReportPath"
