param(
    [string]$ApiBase = "http://127.0.0.1:8750",
    [int]$MinimumAttempts = 30,
    [double]$MinimumSuccessRate = 0.90,
    [int]$SinceMinutes = 0
)

$ErrorActionPreference = "Stop"

$dashboard = Invoke-RestMethod -Uri "$ApiBase/api/dashboard/summary?period=all" -Method Get
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
$discoveredAttachments = if ($dashboard.hotkey_discovered_attachments -ne $null) { [int]$dashboard.hotkey_discovered_attachments } else { 0 }
$contentAvailableAttachments = if ($dashboard.hotkey_content_available_attachments -ne $null) { [int]$dashboard.hotkey_content_available_attachments } else { 0 }
$unknownAttachments = if ($dashboard.hotkey_unknown_attachments -ne $null) { [int]$dashboard.hotkey_unknown_attachments } else { 0 }
$unsupportedAttachments = if ($dashboard.hotkey_unsupported_attachments -ne $null) { [int]$dashboard.hotkey_unsupported_attachments } else { 0 }
$savedTokens = 0
foreach ($record in $hotkeyRecords) {
    $snake = $record.PSObject.Properties["saved_tokens"]
    $camel = $record.PSObject.Properties["savedTokens"]
    if ($null -ne $snake -and $null -ne $snake.Value) {
        $savedTokens += [int]$snake.Value
    }
    elseif ($null -ne $camel -and $null -ne $camel.Value) {
        $savedTokens += [int]$camel.Value
    }
}

$summary = [ordered]@{
    apiBase = $ApiBase
    sinceMinutes = $SinceMinutes
    minimumAttempts = $MinimumAttempts
    minimumSuccessRate = $MinimumSuccessRate
    attempts = $attempts
    successes = $successes
    failures = $failures
    successRate = [Math]::Round($successRate, 4)
    validationStatus = $dashboard.hotkey_validation_status
    latestHotkeyStatus = $dashboard.latest_hotkey_status
    discoveredAttachments = $discoveredAttachments
    contentAvailableAttachments = $contentAvailableAttachments
    unknownAttachments = $unknownAttachments
    unsupportedAttachments = $unsupportedAttachments
    usedAssumedRequests = $dashboard.used_assumed_requests
    optimized = $optimizedRecords.Count
    noSavings = $noSavingsRecords.Count
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
