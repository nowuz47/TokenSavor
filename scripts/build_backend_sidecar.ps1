param(
    [string]$TargetTriple = "aarch64-pc-windows-msvc",
    [ValidateSet("onefile", "onedir")]
    [string]$PackagingMode = "onefile"
)

$ErrorActionPreference = "Stop"

$scriptRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($PSScriptRoot)
$repoRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath((Join-Path $scriptRoot ".."))
$backendDir = Join-Path $repoRoot "backend"
$sidecarDir = Join-Path $repoRoot "frontend\src-tauri\binaries"
$pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"
$versionInfoFile = Join-Path $backendDir "scrooge_backend_version_info.txt"
$sidecarName = "scrooge-backend-$TargetTriple"

if (-not (Test-Path $pythonExe)) {
    throw "Backend virtualenv not found at $pythonExe"
}

New-Item -ItemType Directory -Force -Path $sidecarDir | Out-Null

Push-Location $backendDir
try {
    & $pythonExe -m pip install -e ".[dev]"
    $pyInstallerArgs = @(
        "--clean",
        "--noconfirm",
        "--windowed",
        "--name", $sidecarName,
        "--paths", $backendDir,
        "--collect-submodules", "scrooge",
        "--collect-data", "scrooge",
        "--version-file", $versionInfoFile,
        "--distpath", $sidecarDir,
        "--workpath", (Join-Path $backendDir "build\pyinstaller"),
        "--specpath", (Join-Path $backendDir "build")
    )
    if ($PackagingMode -eq "onefile") {
        $pyInstallerArgs += "--onefile"
    } else {
        $pyInstallerArgs += "--onedir"
    }
    $pyInstallerArgs += "scrooge_backend.py"

    & $pythonExe -m PyInstaller @pyInstallerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }

    if ($PackagingMode -eq "onedir") {
        $oneDirExe = Join-Path (Join-Path $sidecarDir $sidecarName) "$sidecarName.exe"
        if (-not (Test-Path $oneDirExe)) {
            throw "Expected onedir sidecar artifact was not created: $oneDirExe"
        }
        Write-Host "Built backend sidecar directory: $(Split-Path $oneDirExe -Parent)"
        return
    }
}
finally {
    Pop-Location
}

$artifact = Join-Path $sidecarDir "$sidecarName.exe"
if (-not (Test-Path $artifact)) {
    throw "Expected sidecar artifact was not created: $artifact"
}

Write-Host "Built backend sidecar: $artifact"
