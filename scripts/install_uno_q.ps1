[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter()]
    [string]$OfflineBundle = "",

    [Parameter()]
    [string]$DeviceSerial = "",

    [Parameter()]
    [string]$AdbPath = "",

    [Parameter()]
    [switch]$DryRun,

    [Parameter()]
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not $OfflineBundle) {
    $OfflineBundle = Join-Path $projectRoot "artifacts\generated\uno_q\offline-bundle\lightweave-uno"
}
$bundleRoot = (Resolve-Path -LiteralPath $OfflineBundle).Path
$manifestPath = Join-Path $bundleRoot "uno_q.manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "UNO Q bundle manifest is missing: $manifestPath"
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if (
    $manifest.schema_version -ne 1 -or
    $manifest.strict_no_fallback -ne $true -or
    $manifest.strict_audio_suffix_no_fallback -ne $true
) {
    throw "Unsupported or non-strict UNO Q bundle."
}

foreach ($entry in $manifest.files.PSObject.Properties) {
    $relative = $entry.Name.Replace("/", [IO.Path]::DirectorySeparatorChar)
    $path = Join-Path $bundleRoot $relative
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Bundle file is missing: $($entry.Name)"
    }
    $file = Get-Item -LiteralPath $path
    if ($file.Length -ne [int64]$entry.Value.size) {
        throw "Bundle size check failed: $($entry.Name)"
    }
    $actualHash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne [string]$entry.Value.sha256) {
        throw "Bundle hash check failed: $($entry.Name)"
    }
}

if (-not $AdbPath) {
    $candidate = Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"
    if (Test-Path -LiteralPath $candidate) {
        $AdbPath = $candidate
    } else {
        $command = Get-Command adb -ErrorAction SilentlyContinue
        if (-not $command) { throw "adb was not found." }
        $AdbPath = $command.Source
    }
}

$deviceLines = & $AdbPath devices
if (-not $DeviceSerial) {
    $connected = @(
        $deviceLines |
            Select-String '\sdevice$' |
            ForEach-Object { ($_ -split '\s+')[0] }
    )
    if ($connected.Count -ne 1) {
        throw "Expected exactly one connected ADB device; pass -DeviceSerial explicitly."
    }
    $DeviceSerial = $connected[0]
}

$doctor = & $AdbPath -s $DeviceSerial shell "printf 'ARCH='; uname -m; printf '\nAPP_CLI='; arduino-app-cli version 2>/dev/null | head -1; printf '\nFREE_KB='; df -Pk /home/arduino | awk 'NR==2 {print `$4}'"
if ($LASTEXITCODE -ne 0) { throw "Could not inspect the UNO Q." }
$doctorText = $doctor -join "`n"
if ($doctorText -notmatch 'ARCH=aarch64') { throw "Target is not Linux ARM64." }
if ($doctorText -notmatch 'APP_CLI=Arduino App CLI version') { throw "Arduino App CLI is unavailable." }
$freeMatch = [regex]::Match($doctorText, 'FREE_KB=(\d+)')
if (-not $freeMatch.Success -or [int64]$freeMatch.Groups[1].Value -lt 131072) {
    throw "UNO Q has less than 128 MiB free disk space."
}

$target = "/home/arduino/ArduinoApps/lightweave-uno"
Write-Host "Device: $DeviceSerial"
Write-Host "Bundle: $bundleRoot"
Write-Host "Target: $target"
Write-Host "Runner SHA-256: $($manifest.runner_sha256)"
if ($DryRun) {
    Write-Host "Dry run passed; no board files were changed."
    exit 0
}

$suffix = [guid]::NewGuid().ToString("N").Substring(0, 10)
$stage = "/tmp/lightweave-uno-install-$suffix"
& $AdbPath -s $DeviceSerial shell "mkdir -p '$stage'"
if ($LASTEXITCODE -ne 0) { throw "Could not create the remote staging directory." }
& $AdbPath -s $DeviceSerial push $bundleRoot "$stage/lightweave-uno"
if ($LASTEXITCODE -ne 0) { throw "Could not upload the UNO Q bundle." }

$remoteInstall = @"
set -eu
mkdir -p '$target'
cp -a '$stage/lightweave-uno/.' '$target/'
chmod 755 '$target/lightweave-uno' '$target/runtime/lightweave-uno-runner'
test -f /lib/aarch64-linux-gnu/libvulkan.so.1
test -f /usr/lib/aarch64-linux-gnu/libvulkan_freedreno.so
test -f /usr/share/vulkan/icd.d/freedreno_icd.json
mkdir -p '$target/runtime/vulkan'
cp -L /lib/aarch64-linux-gnu/libvulkan.so.1 '$target/runtime/vulkan/libvulkan.so.1'
cp -L /usr/lib/aarch64-linux-gnu/libvulkan_freedreno.so '$target/runtime/vulkan/libvulkan_freedreno.so'
cp /usr/share/vulkan/icd.d/freedreno_icd.json '$target/runtime/vulkan/freedreno_icd.json'
chmod 644 '$target/runtime/vulkan/'*
touch '$target/runtime/.accelerator.lock'
chmod 666 '$target/runtime/.accelerator.lock'
mkdir -p /home/arduino/.local/bin
ln -sfn '$target/lightweave-uno' /home/arduino/.local/bin/lightweave-uno
rm -rf '$stage'
'$target/lightweave-uno' doctor --json
"@
& $AdbPath -s $DeviceSerial shell $remoteInstall
if ($LASTEXITCODE -ne 0) { throw "UNO Q installation or native doctor failed." }

if (-not $NoStart) {
    & $AdbPath -s $DeviceSerial shell "arduino-app-cli app restart '$target'"
    if ($LASTEXITCODE -ne 0) { throw "App Lab could not restart LightWeave UNO Q." }
}

Write-Host "LightWeave UNO Q installation completed."
