param(
    [Parameter(Mandatory = $true)]
    [string[]]$ArtifactPath,
    [switch]$RequireSigned,
    [switch]$ScanWithDefender
)

$ErrorActionPreference = "Stop"

function Get-ArtifactFiles {
    param([string[]]$Paths)

    foreach ($path in $Paths) {
        if (-not (Test-Path -LiteralPath $path)) {
            throw "Artifact path does not exist: $path"
        }

        $item = Get-Item -LiteralPath $path
        if ($item.PSIsContainer) {
            Get-ChildItem -LiteralPath $item.FullName -Recurse -File |
                Where-Object { $_.Extension -in @(".exe", ".msi") }
        }
        else {
            $item
        }
    }
}

$files = @(Get-ArtifactFiles -Paths $ArtifactPath)
if ($files.Count -eq 0) {
    throw "No .exe or .msi artifacts found."
}

$defenderAvailable = $false
try {
    $defenderStatus = Get-MpComputerStatus -ErrorAction Stop
    $defenderAvailable = $true
    Write-Host "Microsoft Defender: AMServiceEnabled=$($defenderStatus.AMServiceEnabled), AntivirusEnabled=$($defenderStatus.AntivirusEnabled), AntispywareEnabled=$($defenderStatus.AntispywareEnabled)"
}
catch {
    Write-Warning "Microsoft Defender status is unavailable on this machine."
}

$failed = $false
foreach ($file in $files) {
    $hash = Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256
    $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
    $status = $signature.Status.ToString()
    $subject = if ($signature.SignerCertificate) { $signature.SignerCertificate.Subject } else { "" }

    Write-Host "Artifact: $($file.FullName)"
    Write-Host "  SHA256: $($hash.Hash.ToLowerInvariant())"
    Write-Host "  Signature: $status"
    if ($subject) {
        Write-Host "  Signer: $subject"
    }

    if ($RequireSigned -and $signature.Status -ne "Valid") {
        Write-Error "Required valid Authenticode signature is missing or invalid: $($file.FullName)"
        $failed = $true
    }

    if ($ScanWithDefender -and $defenderAvailable) {
        try {
            Start-MpScan -ScanType CustomScan -ScanPath $file.FullName -ErrorAction Stop
            Write-Host "  Defender custom scan: completed"
        }
        catch {
            Write-Error "  Defender custom scan failed: $($_.Exception.Message)"
            $failed = $true
        }
    }
}

if ($failed) {
    exit 1
}

if (-not $RequireSigned) {
    Write-Warning "Unsigned artifacts can still trigger SmartScreen or antivirus reputation warnings on other computers. Use -RequireSigned for release gating once a code-signing certificate is available."
}
