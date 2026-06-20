param(
    [string]$TargetTriple = "x86_64-pc-windows-msvc",
    [string]$ApiBase = "http://127.0.0.1:8750",
    [string]$NodePath = "C:\Users\juwonkim\AppData\Local\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.17.0-win-arm64",
    [string]$CargoTargetDir = "",
    [switch]$SkipInstall,
    [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"

$scriptRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($PSScriptRoot)
$repoRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath((Join-Path $scriptRoot ".."))
$frontendDir = Join-Path $repoRoot "frontend"
$vsDevCmd = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat"

if (-not $CargoTargetDir) {
    $CargoTargetDir = Join-Path $env:TEMP "scrooge-tauri-target-$TargetTriple"
}

function Invoke-CmdChecked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    $process = Start-Process `
        -FilePath $env:COMSPEC `
        -ArgumentList "/d", "/s", "/c", $Command `
        -NoNewWindow `
        -Wait `
        -PassThru

    if ($process.ExitCode -ne 0) {
        throw "$Label failed with exit code $($process.ExitCode)"
    }
}

Stop-Process -Name "Scrooge" -ErrorAction SilentlyContinue
Stop-Process -Name "scrooge-backend" -ErrorAction SilentlyContinue

& (Join-Path $scriptRoot "build_backend_sidecar.ps1") -TargetTriple $TargetTriple
if ($LASTEXITCODE -ne 0) {
    throw "Backend sidecar build failed with exit code $LASTEXITCODE"
}

$frontendBuildDir = Join-Path $env:TEMP ("scrooge-tauri-src-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $frontendBuildDir | Out-Null
foreach ($item in @("package.json", "package-lock.json", "index.html", "tsconfig.json", "vite.config.ts", "src", "public", "src-tauri")) {
    Copy-Item -Path (Join-Path $frontendDir $item) -Destination $frontendBuildDir -Recurse -Force
}

$hostArch = if ($TargetTriple -like "x86_64*") { "x64" } else { "arm64" }
$buildCommand = @(
    "set `"PATH=$NodePath;C:\Users\juwonkim\.cargo\bin;%PATH%`"",
    "call `"$vsDevCmd`" -arch=$hostArch -host_arch=arm64 >nul",
    "set `"RUSTUP_TOOLCHAIN=stable-$TargetTriple`"",
    "set `"CARGO_TARGET_DIR=$CargoTargetDir`"",
    "pushd `"$frontendBuildDir`"",
    "npm.cmd ci --prefer-offline --no-audit --no-fund",
    "npx.cmd tauri build --target $TargetTriple",
    "popd"
) -join " && "

try {
    Invoke-CmdChecked -Command $buildCommand -Label "Tauri installer build"
}
finally {
    Remove-Item -Path $frontendBuildDir -Recurse -Force -ErrorAction SilentlyContinue
}

$installer = Get-ChildItem -Path $CargoTargetDir -Recurse -Filter "*setup.exe" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $installer) {
    throw "No installer was produced under $CargoTargetDir"
}

Write-Host "Built installer: $($installer.FullName)"

if (-not $SkipInstall) {
    Start-Process -FilePath $installer.FullName -ArgumentList "/S" -Wait

    $exeCandidates = @(
        (Join-Path $env:LOCALAPPDATA "Scrooge\Scrooge.exe"),
        (Join-Path $env:ProgramFiles "Scrooge\Scrooge.exe")
    )
    $appExe = $exeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $appExe) {
        throw "Installed Scrooge executable was not found."
    }

    Start-Process -FilePath $appExe -WindowStyle Hidden

    $runtime = $null
    $deadline = (Get-Date).AddSeconds(45)
    do {
        try {
            $runtime = Invoke-RestMethod -Uri "$ApiBase/api/runtime/status" -Method Get
            break
        }
        catch {
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)

    if ($null -eq $runtime) {
        throw "Installed runtime check failed: backend did not become ready."
    }

    if ($runtime.backend_status -ne "ok" -or $runtime.database_status -ne "ok") {
        throw "Installed runtime check failed: $($runtime | ConvertTo-Json -Compress)"
    }
}

if (-not $SkipSmoke) {
    & (Join-Path $scriptRoot "verify_install_smoke.ps1") -ApiBase $ApiBase
    if ($LASTEXITCODE -ne 0) {
        throw "Install smoke failed with exit code $LASTEXITCODE"
    }
}

Write-Host "Build, reinstall, and verification completed."
