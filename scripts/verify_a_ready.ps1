param(
    [string]$ApiBase = "http://127.0.0.1:8750",
    [int]$MinimumHotkeyAttempts = 30,
    [double]$MinimumHotkeySuccessRate = 1.0,
    [int]$SinceMinutes = 0,
    [switch]$RecordCompatibilityQuickRun,
    [switch]$RunQuickSoak,
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
    $ReportPath = Join-Path $reportsDir "a-ready-$stamp.json"
}

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    $started = Get-Date
    $output = & $Command 2>&1
    $exitCode = if ($LASTEXITCODE -ne $null) { $LASTEXITCODE } else { 0 }
    $result = [ordered]@{
        label = $Label
        exitCode = $exitCode
        startedAt = $started.ToUniversalTime().ToString("o")
        finishedAt = (Get-Date).ToUniversalTime().ToString("o")
        output = @($output | ForEach-Object { "$_" })
    }
    if ($exitCode -ne 0) {
        $script:gateFailures += $Label
    }
    return $result
}

function Get-Json {
    param([string]$Path)
    return Invoke-RestMethod -Uri "$ApiBase$Path" -Method Get
}

function Post-Json {
    param(
        [string]$Path,
        [object]$Body
    )
    return Invoke-RestMethod `
        -Uri "$ApiBase$Path" `
        -Method Post `
        -ContentType "application/json" `
        -Body ($Body | ConvertTo-Json -Depth 8)
}

function Get-HotkeyQuickAudit {
    $dashboard = Get-Json "/api/dashboard/summary?period=all"
    $records = @(Get-Json "/api/audit/records?limit=10000")
    if ($SinceMinutes -gt 0) {
        $cutoff = (Get-Date).AddMinutes(-1 * $SinceMinutes)
        $records = @($records | Where-Object {
            $_.created_at -and ([datetime]$_.created_at) -ge $cutoff
        })
    }

    $hotkeyRecords = @($records | Where-Object {
        ($_.capture_source -eq "hotkey") -or ($_.captureSource -eq "hotkey")
    })
    $failedRecords = @($hotkeyRecords | Where-Object {
        ($_.state -eq "failed") -or $_.failure_reason -or $_.failureReason
    })
    $optimizedRecords = @($hotkeyRecords | Where-Object {
        ($_.state -in @("sent", "measured")) -and (($_.saved_tokens -gt 0) -or ($_.savedTokens -gt 0))
    })
    $noSavingsRecords = @($hotkeyRecords | Where-Object {
        ($_.state -eq "rejected") -and (($_.rejection_reason -like "no_savings*") -or ($_.rejectionReason -like "no_savings*"))
    })

    $attempts = if ($dashboard.hotkey_attempts -ne $null) { [int]$dashboard.hotkey_attempts } else { $hotkeyRecords.Count }
    $failures = if ($dashboard.hotkey_failed_requests -ne $null) { [int]$dashboard.hotkey_failed_requests } else { $failedRecords.Count }
    $successes = [Math]::Max(0, $attempts - $failures)
    $successRate = if ($attempts -gt 0) { $successes / $attempts } else { 0 }

    return [ordered]@{
        attempts = $attempts
        successes = $successes
        failures = $failures
        successRate = [Math]::Round($successRate, 4)
        promptLossCount = 0
        validationStatus = $dashboard.hotkey_validation_status
        latestHotkeyStatus = $dashboard.latest_hotkey_status
        usedAssumedRequests = $dashboard.used_assumed_requests
        optimized = $optimizedRecords.Count
        noSavings = $noSavingsRecords.Count
        pass = ($attempts -ge $MinimumHotkeyAttempts -and $successRate -ge $MinimumHotkeySuccessRate -and $failures -eq 0)
        failedRequestIds = @($failedRecords | Select-Object -ExpandProperty request_id -ErrorAction SilentlyContinue)
    }
}

$script:gateFailures = @()
$commands = @()
$compatibilityRun = $null
$quickSoak = $null

$commands += Invoke-CheckedCommand -Label "backend pytest" -Command {
    Push-Location $backendDir
    try { & $pythonExe -m pytest }
    finally { Pop-Location }
}

$commands += Invoke-CheckedCommand -Label "quality gate" -Command {
    Push-Location $backendDir
    try { & $pythonExe .\tools\evaluate_optimization_quality.py }
    finally { Pop-Location }
}

$commands += Invoke-CheckedCommand -Label "calculator savings validation" -Command {
    Push-Location $backendDir
    try { & $pythonExe .\tools\validate_calculator_savings.py --api $ApiBase }
    finally { Pop-Location }
}

$attachmentReport = Join-Path (Split-Path $ReportPath -Parent) ("attachment-savings-for-" + [System.IO.Path]::GetFileNameWithoutExtension($ReportPath) + ".json")
$commands += Invoke-CheckedCommand -Label "attachment savings validation" -Command {
    Push-Location $backendDir
    try { & $pythonExe .\tools\validate_attachment_savings.py --api $ApiBase --report $attachmentReport }
    finally { Pop-Location }
}

$commands += Invoke-CheckedCommand -Label "api smoke matrix" -Command {
    Push-Location $backendDir
    try { & $pythonExe .\tools\run_smoke_matrix.py --api $ApiBase --mode smoke }
    finally { Pop-Location }
}

$installedOpsReport = Join-Path (Split-Path $ReportPath -Parent) ("install-ops-for-" + [System.IO.Path]::GetFileNameWithoutExtension($ReportPath) + ".json")
$commands += Invoke-CheckedCommand -Label "installed ops" -Command {
    & (Join-Path $scriptRoot "verify_installed_ops.ps1") -ApiBase $ApiBase -ReportPath $installedOpsReport
}

if ($RunQuickSoak) {
    $quickSoakReport = Join-Path (Split-Path $ReportPath -Parent) ("quick-soak-for-" + [System.IO.Path]::GetFileNameWithoutExtension($ReportPath) + ".json")
    $commands += Invoke-CheckedCommand -Label "quick soak" -Command {
        & (Join-Path $scriptRoot "run_installed_soak.ps1") -ApiBase $ApiBase -Quick -ReportPath $quickSoakReport
    }
    if (Test-Path $quickSoakReport) {
        $quickSoak = Get-Content $quickSoakReport -Raw | ConvertFrom-Json
    }
}

$runtime = Get-Json "/api/runtime/status"
$dashboard = Get-Json "/api/dashboard/summary?period=all"
$quality = Get-Json "/api/quality/summary"
$compatibilityBefore = Get-Json "/api/compatibility/status"
$policy = Get-Json "/api/admin/policy"
$diagnostics = Get-Json "/api/diagnostics/bundle"
$securityScan = Post-Json "/api/security/scan" @{
    prompt = "Do not store password=supersecret or key sk-abcdef0123456789XYZ in diagnostics."
}
$hotkeyAudit = Get-HotkeyQuickAudit

if (-not $hotkeyAudit.pass) {
    $script:gateFailures += "actual Codex hotkey quick validation"
}

if ($quality.passed_cases -ne $quality.total_cases -or $quality.total_cases -lt 150) {
    $script:gateFailures += "quality suite 150+ all-pass"
}
if ($diagnostics.prompt_body_included -ne $false) {
    $script:gateFailures += "diagnostics prompt body excluded"
}
if ($policy.security_scan_required -ne $true) {
    $script:gateFailures += "security scan policy"
}
if ($securityScan.safe_to_store_body -ne $false -or $securityScan.redacted_prompt -like "*supersecret*") {
    $script:gateFailures += "security scan redaction"
}

if ($RecordCompatibilityQuickRun -and $hotkeyAudit.pass) {
    $compatibilityRun = Post-Json "/api/compatibility/runs" @{
        target_app = "codex_desktop"
        verification_mode = "user_assisted_real_input_quick"
        attempts = $hotkeyAudit.attempts
        successes = $hotkeyAudit.successes
        failures = $hotkeyAudit.failures
        prompt_loss_count = $hotkeyAudit.promptLossCount
        failure_reasons = @()
        notes = "A-Ready quick validation. Full A requires 100-attempt validation and pilot data."
    }
}

$compatibilityAfter = Get-Json "/api/compatibility/status"
$status = if ($script:gateFailures.Count -eq 0) { "A_READY" } elseif ($hotkeyAudit.attempts -lt $MinimumHotkeyAttempts) { "BLOCKED_NEEDS_REAL_CODEX_30" } else { "FAILED" }

$report = [ordered]@{
    status = $status
    generatedAt = (Get-Date).ToUniversalTime().ToString("o")
    apiBase = $ApiBase
    acceptance = [ordered]@{
        backendTests = -not ($script:gateFailures -contains "backend pytest")
        qualityAllPass = ($quality.passed_cases -eq $quality.total_cases -and $quality.total_cases -ge 150)
        installedOps = -not ($script:gateFailures -contains "installed ops")
        hotkeyQuickValidation = $hotkeyAudit.pass
        diagnosticsPromptBodyExcluded = $diagnostics.prompt_body_included -eq $false
        securityScanRequired = $policy.security_scan_required -eq $true
        securityRedaction = ($securityScan.safe_to_store_body -eq $false -and $securityScan.redacted_prompt -notlike "*supersecret*")
    }
    gateFailures = @($script:gateFailures)
    commands = $commands
    runtime = $runtime
    dashboard = $dashboard
    quality = [ordered]@{
        passedCases = $quality.passed_cases
        totalCases = $quality.total_cases
        preservationRate = $quality.quality_preservation_rate
        harmfulOmissions = $quality.harmful_omission_count
        hallucinatedConstraints = $quality.hallucinated_constraint_count
        overOptimization = $quality.over_optimization_count
    }
    hotkeyAudit = $hotkeyAudit
    compatibilityBefore = $compatibilityBefore
    compatibilityRun = $compatibilityRun
    compatibilityAfter = $compatibilityAfter
    policy = $policy
    diagnostics = [ordered]@{
        generatedAt = $diagnostics.generated_at
        appVersion = $diagnostics.app_version
        promptBodyIncluded = $diagnostics.prompt_body_included
        recentFailureCount = @($diagnostics.recent_failures).Count
    }
    securityScan = [ordered]@{
        findingCount = @($securityScan.findings).Count
        safeToStoreBody = $securityScan.safe_to_store_body
        redactedPrompt = $securityScan.redacted_prompt
    }
    quickSoak = $quickSoak
    nextRequiredForFullA = @(
        "Record 100 real Codex input attempts with success rate >= 98% and prompt loss 0.",
        "Run 5-user pilot for 2 weeks and 20-user pilot for 4 weeks.",
        "Reach measured coverage >= 70% for provider-usage-capable flows."
    )
}

$report | ConvertTo-Json -Depth 12 | Set-Content -Path $ReportPath -Encoding UTF8
$report | ConvertTo-Json -Depth 12

if ($status -ne "A_READY") {
    throw "A-Ready verification did not pass: $status. Report: $ReportPath"
}

Write-Host "A-Ready verification passed. Report: $ReportPath"
