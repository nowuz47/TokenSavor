param(
    [string]$TargetTriple = "aarch64-pc-windows-msvc"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$backendDir = Join-Path $repoRoot "backend"
$sidecarDir = Join-Path $repoRoot "frontend\src-tauri\binaries"
$pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"
$sidecarName = "scrooge-backend-$TargetTriple"

if (-not (Test-Path $pythonExe)) {
    throw "Backend virtualenv not found at $pythonExe"
}

New-Item -ItemType Directory -Force -Path $sidecarDir | Out-Null

Push-Location $backendDir
try {
    & $pythonExe -m pip install -e ".[dev]"
    & $pythonExe -m PyInstaller `
        --clean `
        --noconfirm `
        --onefile `
        --name $sidecarName `
        --paths $backendDir `
        --collect-submodules scrooge `
        --collect-data scrooge `
        --distpath $sidecarDir `
        --workpath (Join-Path $backendDir "build\pyinstaller") `
        --specpath (Join-Path $backendDir "build") `
        scrooge_backend.py
}
finally {
    Pop-Location
}

$artifact = Join-Path $sidecarDir "$sidecarName.exe"
if (-not (Test-Path $artifact)) {
    throw "Expected sidecar artifact was not created: $artifact"
}

Write-Host "Built backend sidecar: $artifact"
