param(
    [string]$ApiBase = "http://127.0.0.1:8750",
    [int]$MinimumAttempts = 30,
    [double]$MinimumSuccessRate = 0.90,
    [int]$SinceMinutes = 0
)

$ErrorActionPreference = "Stop"

$records = @(Invoke-RestMethod -Uri "$ApiBase/api/audit/records?limit=10000" -Method Get)
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

$attempts = $hotkeyRecords.Count
$successes = [Math]::Max(0, $attempts - $failedRecords.Count)
$successRate = if ($attempts -gt 0) { $successes / $attempts } else { 0 }
$savedTokens = ($hotkeyRecords | Measure-Object -Property saved_tokens -Sum).Sum
if ($null -eq $savedTokens) {
    $savedTokens = ($hotkeyRecords | Measure-Object -Property savedTokens -Sum).Sum
}
if ($null -eq $savedTokens) {
    $savedTokens = 0
}

$summary = [ordered]@{
    apiBase = $ApiBase
    sinceMinutes = $SinceMinutes
    minimumAttempts = $MinimumAttempts
    minimumSuccessRate = $MinimumSuccessRate
    attempts = $attempts
    successes = $successes
    failures = $failedRecords.Count
    successRate = [Math]::Round($successRate, 4)
    savedTokens = [int]$savedTokens
    failedRequestIds = @($failedRecords | Select-Object -ExpandProperty request_id -ErrorAction SilentlyContinue)
}

$summary | ConvertTo-Json -Depth 4

if ($attempts -lt $MinimumAttempts) {
    throw "Hotkey audit attempts are below threshold: $attempts < $MinimumAttempts"
}

if ($successRate -lt $MinimumSuccessRate) {
    throw "Hotkey success rate is below threshold: $successRate < $MinimumSuccessRate"
}

Write-Host "Hotkey audit validation passed."
