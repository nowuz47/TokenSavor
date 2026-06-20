param(
    [string]$ApiBase = "http://127.0.0.1:8750",
    [string]$ReportPath = ""
)

$ErrorActionPreference = "Stop"

$scriptRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($PSScriptRoot)
$repoRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath((Join-Path $scriptRoot ".."))

if (-not $ReportPath) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $reportsDir = Join-Path $repoRoot "reports"
    New-Item -ItemType Directory -Force -Path $reportsDir | Out-Null
    $ReportPath = Join-Path $reportsDir "install-ops-$stamp.json"
}

$runtime = Invoke-RestMethod -Uri "$ApiBase/api/runtime/status" -Method Get
$summary = Invoke-RestMethod -Uri "$ApiBase/api/dashboard/summary?period=all" -Method Get
$compatibility = Invoke-RestMethod -Uri "$ApiBase/api/compatibility/status" -Method Get
$policy = Invoke-RestMethod -Uri "$ApiBase/api/admin/policy" -Method Get
$diagnostics = Invoke-RestMethod -Uri "$ApiBase/api/diagnostics/bundle" -Method Get
$scroogeProcesses = @(Get-Process -Name "Scrooge", "scrooge" -ErrorAction SilentlyContinue)
$backendProcesses = @(Get-Process -Name "scrooge-backend" -ErrorAction SilentlyContinue)
$cmdProcesses = @(Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -in @("cmd.exe", "conhost.exe")) -and ($_.CommandLine -like "*Scrooge*")
})

$dbPath = $runtime.database_path
if ($dbPath -and $dbPath -ne ":memory:" -and -not [System.IO.Path]::IsPathRooted($dbPath)) {
    $installedLocal = Join-Path $env:LOCALAPPDATA "Scrooge"
    $candidate = Join-Path $installedLocal $dbPath
    if (Test-Path $candidate) {
        $dbPath = $candidate
    }
}

$checks = [ordered]@{
    appProcessRunning = $scroogeProcesses.Count -ge 1
    backendProcessRunning = $backendProcesses.Count -ge 1
    backendStatusOk = $runtime.backend_status -eq "ok"
    databaseStatusOk = $runtime.database_status -eq "ok"
    hotkeyRegistered = $runtime.hotkey_status -eq "registered"
    sidecarManaged = $runtime.sidecar_status -eq "managed"
    databasePath = $runtime.database_path
    databaseExists = if ($dbPath -and $dbPath -ne ":memory:") { Test-Path $dbPath } else { $true }
    noScroogeCmdWindow = $cmdProcesses.Count -eq 0
    hotkeyValidationStatus = $summary.hotkey_validation_status
    hotkeyAttempts = $summary.hotkey_attempts
    usedAssumedRequests = $summary.used_assumed_requests
    compatibilityStatus = $compatibility.overall_status
    diagnosticsPromptBodyExcluded = $diagnostics.prompt_body_included -eq $false
    securityScanRequired = $policy.security_scan_required -eq $true
}

$report = [ordered]@{
    apiBase = $ApiBase
    checkedAt = (Get-Date).ToUniversalTime().ToString("o")
    runtime = $runtime
    summary = $summary
    compatibility = $compatibility
    policy = $policy
    diagnostics = $diagnostics
    checks = $checks
    processes = [ordered]@{
        scrooge = @($scroogeProcesses | Select-Object ProcessName, Id, MainWindowTitle)
        backend = @($backendProcesses | Select-Object ProcessName, Id, MainWindowTitle)
        cmdLike = @($cmdProcesses | Select-Object ProcessId, ParentProcessId, Name, CommandLine)
    }
}

$report | ConvertTo-Json -Depth 8 | Set-Content -Path $ReportPath -Encoding UTF8
$report | ConvertTo-Json -Depth 8

$failed = @(
    $checks.appProcessRunning,
    $checks.backendProcessRunning,
    $checks.backendStatusOk,
    $checks.databaseStatusOk,
    $checks.hotkeyRegistered,
    $checks.sidecarManaged,
    $checks.databaseExists,
    $checks.noScroogeCmdWindow,
    $checks.diagnosticsPromptBodyExcluded,
    $checks.securityScanRequired
) | Where-Object { -not $_ }

if ($failed.Count -gt 0) {
    throw "Installed ops verification failed. Report: $ReportPath"
}

Write-Host "Installed ops verification passed. Report: $ReportPath"
