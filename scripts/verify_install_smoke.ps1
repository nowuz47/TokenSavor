param(
    [string]$ApiBase = "http://127.0.0.1:8750"
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"
$pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"
$nodePath = "C:\Users\juwonkim\AppData\Local\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.17.0-win-arm64"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

Push-Location $backendDir
try {
    Invoke-Checked { & $pythonExe -m pytest } "Backend tests"
    Invoke-Checked { & $pythonExe .\tools\evaluate_optimization_quality.py } "Optimization quality gate"
    Invoke-Checked { & $pythonExe .\tools\validate_calculator_savings.py --api $ApiBase } "Calculator savings validation"
}
finally {
    Pop-Location
}

Push-Location $frontendDir
try {
    Invoke-Checked { cmd /c "set PATH=$nodePath;%PATH%&& $nodePath\npm.cmd run build" } "Frontend build"
}
finally {
    Pop-Location
}

Write-Host "Scrooge smoke and reliability checks passed."
