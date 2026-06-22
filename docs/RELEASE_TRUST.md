# Windows Release Trust Checklist

Scrooge uses a Tauri desktop shell and a PyInstaller backend sidecar. That combination is legitimate, but unsigned fresh binaries can still be flagged by SmartScreen or antivirus reputation systems on another computer.

This checklist reduces false-positive risk before publishing a Windows installer.

## Required For Public Releases

1. Build from a clean Git tag.
2. Sign the Windows installer and signable application binaries with a trusted code-signing certificate.
3. Timestamp the signature.
4. Verify Authenticode signatures before upload.
5. Publish SHA256 hashes with the release.
6. Keep the same publisher identity across releases so reputation can accumulate.
7. If Microsoft Defender reports malware or PUA, submit the exact artifact to Microsoft Security Intelligence as a software developer.

## Configure Signing

The build script reads these environment variables and injects them only into the temporary Tauri build config:

```powershell
$env:SCROOGE_WINDOWS_CERT_THUMBPRINT = "<certificate thumbprint>"
$env:SCROOGE_WINDOWS_DIGEST_ALGORITHM = "sha256"
$env:SCROOGE_WINDOWS_TIMESTAMP_URL = "http://timestamp.digicert.com"
```

Alternatively, provide a custom signing command:

```powershell
$env:SCROOGE_WINDOWS_SIGN_COMMAND = "trusted-signing-cli -e <endpoint> -a <account> -c <profile> -d Scrooge %1"
```

Then build with release gating:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_reinstall_verify.ps1 -RequireSigned
```

## Verify Existing Artifacts

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_release_trust.ps1 `
  -ArtifactPath "frontend\src-tauri\target\release\bundle\nsis" `
  -RequireSigned `
  -ScanWithDefender
```

The script prints:

- SHA256 hash
- Authenticode signature status
- signer subject
- Microsoft Defender availability
- optional Defender custom scan result

## Why This Matters

- SmartScreen reputation is not a manual allowlist. It is built from signed files, certificate reputation, download history, and Microsoft telemetry.
- Unsigned binaries rebuild reputation from zero for every changed hash.
- Signing does not guarantee zero prompts, but it lets Windows show a verified publisher and lets reputation attach to the publisher certificate over time.
- PyInstaller one-file executables are more likely to look unusual to reputation systems than ordinary signed application binaries, so the sidecar must also have clear version metadata and should be signed in mature releases.

## Current Limitation

The repository cannot include a real private signing key or certificate. Until a trusted certificate or Azure Trusted Signing profile is configured, public Windows builds should be treated as alpha/test artifacts rather than low-friction enterprise deployment packages.
