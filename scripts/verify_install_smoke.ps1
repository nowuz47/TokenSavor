param(
    [string]$ApiBase = "http://127.0.0.1:8750"
)

$ErrorActionPreference = "Stop"
$scriptRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($PSScriptRoot)
$repoRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath((Join-Path $scriptRoot ".."))
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

function Invoke-FrontendBuild {
    $tempRoot = Join-Path $env:TEMP ("scrooge-frontend-build-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null

    try {
        foreach ($item in @("package.json", "package-lock.json", "index.html", "tsconfig.json", "vite.config.ts", "src", "public")) {
            Copy-Item -Path (Join-Path $frontendDir $item) -Destination $tempRoot -Recurse -Force
        }

        Push-Location $tempRoot
        try {
            $env:PATH = "$nodePath;$env:PATH"
            Invoke-Checked { & "$nodePath\npm.cmd" ci --prefer-offline --no-audit --no-fund } "Frontend npm ci"
            Invoke-Checked { & "$nodePath\npm.cmd" run build } "Frontend build"
        }
        finally {
            Pop-Location
        }
    }
    finally {
        Remove-Item -Path $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Push-Location $backendDir
try {
    Invoke-Checked { & $pythonExe -m pytest } "Backend tests"
    Invoke-Checked { & $pythonExe .\tools\evaluate_optimization_quality.py } "Optimization quality gate"
    Invoke-Checked { & $pythonExe .\tools\validate_calculator_savings.py --api $ApiBase } "Calculator savings validation"
    Invoke-Checked { & $pythonExe .\tools\run_smoke_matrix.py --api $ApiBase --mode smoke } "Installed API smoke matrix"
}
finally {
    Pop-Location
}

$runtime = Invoke-RestMethod -Uri "$ApiBase/api/runtime/status" -Method Get
if ($runtime.backend_status -ne "ok" -or $runtime.database_status -ne "ok") {
    throw "Runtime status check failed: $($runtime | ConvertTo-Json -Compress)"
}

Invoke-FrontendBuild

Write-Host "Scrooge smoke and reliability checks passed."
