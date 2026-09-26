[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter()]
    [string]$DeviceSerial = "",

    [Parameter()]
    [string]$AdbPath = "",

    [Parameter()]
    [switch]$DryRun,

    [Parameter()]
    [switch]$NoStart,

    [Parameter()]
    [switch]$StopRunningApp
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$trackedRoot = (Resolve-Path (Join-Path $projectRoot "uno_q\parallel_receiver_app")).Path
$frameHeader = (Resolve-Path (Join-Path $projectRoot "uno_q\common\lightweave_optical_frame.h")).Path
$parallelHeader = (Resolve-Path (Join-Path $projectRoot "uno_q\common\lightweave_parallel_optical.h")).Path
$sourceApp = "/home/arduino/ArduinoApps/lightweave_receiver"
$targetApp = "/home/arduino/ArduinoApps/lightweave_parallel_receiver"
$targetDisplayName = "LightWeave Parallel Receiver"
$requiredFiles = @(
    "app.yaml",
    "README.md",
    "parallel_receiver.manifest.json",
    "sketch/sketch.ino",
    "sketch/sketch.yaml"
)

foreach ($relative in $requiredFiles) {
    $local = Join-Path $trackedRoot $relative.Replace("/", [IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path -LiteralPath $local -PathType Leaf)) {
        throw "Tracked parallel-receiver file is missing: $relative"
    }
}
foreach ($shared in @($frameHeader, $parallelHeader)) {
    if (-not (Test-Path -LiteralPath $shared -PathType Leaf)) {
        throw "Shared optical sketch header is missing: $shared"
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
$AdbPath = (Resolve-Path -LiteralPath $AdbPath).Path

if (-not $DeviceSerial) { $DeviceSerial = $env:LIGHTWEAVE_UNO_Q_RECEIVER_SERIAL }
if (-not $DeviceSerial) {
    throw "Pass -DeviceSerial or set LIGHTWEAVE_UNO_Q_RECEIVER_SERIAL."
}
$authorized = @(
    (& $AdbPath devices) |
        Select-String '\sdevice$' |
        ForEach-Object { ($_ -split '\s+')[0] }
)
if ($DeviceSerial -notin $authorized) {
    throw "Receiver UNO Q $DeviceSerial is not connected and authorized."
}

$doctor = & $AdbPath -s $DeviceSerial shell "printf 'ARCH='; uname -m; printf '\nAPP_CLI='; arduino-app-cli version 2>/dev/null | head -1; printf '\nFREE_KB='; df -Pk /home/arduino | awk 'NR==2 {print `$4}'"
if ($LASTEXITCODE -ne 0) { throw "Could not inspect the receiver UNO Q." }
$doctorText = $doctor -join "`n"
if ($doctorText -notmatch 'ARCH=aarch64') { throw "Target is not Linux ARM64." }
if ($doctorText -notmatch 'APP_CLI=Arduino App CLI version') {
    throw "Arduino App CLI is unavailable."
}
$freeMatch = [regex]::Match($doctorText, 'FREE_KB=(\d+)')
if (-not $freeMatch.Success -or [int64]$freeMatch.Groups[1].Value -lt 262144) {
    throw "UNO Q has less than 256 MiB free disk space for a receiver clone."
}

$sourceFiles = @(
    "$sourceApp/app.yaml",
    "$sourceApp/optical_receiver.manifest.json",
    "$sourceApp/python/main.py",
    "$sourceApp/python/lightweave_optical_receiver.py",
    "$sourceApp/python/phone_usb.py",
    "$sourceApp/sketch/sketch.ino",
    "$sourceApp/runtime/lightweave-uno-runner"
)
foreach ($remote in $sourceFiles) {
    & $AdbPath -s $DeviceSerial shell "test -f '$remote'"
    if ($LASTEXITCODE -ne 0) {
        throw "The standard receiver must be installed first: $remote"
    }
}
$hashCommand = "sha256sum " + (($sourceFiles | ForEach-Object { "'$_'" }) -join " ")
$sourceBefore = (& $AdbPath -s $DeviceSerial shell $hashCommand) -join "`n"
if ($LASTEXITCODE -ne 0 -or -not $sourceBefore) {
    throw "Could not hash the standard receiver."
}

& $AdbPath -s $DeviceSerial shell "test -d '$targetApp'"
$targetExists = $LASTEXITCODE -eq 0
if ($targetExists) {
    & $AdbPath -s $DeviceSerial shell "test -f '$targetApp/parallel_receiver.manifest.json'"
    if ($LASTEXITCODE -ne 0) {
        throw "Refusing to overwrite an unrelated lightweave_parallel_receiver app."
    }
}

Write-Host "Device: $DeviceSerial"
Write-Host "Source app: lightweave_receiver (read-only)"
Write-Host "Target app: lightweave_parallel_receiver / $targetDisplayName"
Write-Host "Sketch lanes: A0, A2, A5"
if ($DryRun) {
    Write-Host "Dry run passed; the board was not modified."
    exit 0
}

if (-not $targetExists) {
    & $AdbPath -s $DeviceSerial shell "arduino-app-cli app new lightweave_parallel_receiver --from-app '$sourceApp'"
    if ($LASTEXITCODE -ne 0) { throw "Could not clone the standard receiver." }
}

$stage = "/tmp/lightweave-parallel-rx-$([guid]::NewGuid().ToString('N').Substring(0, 10))"
& $AdbPath -s $DeviceSerial shell "mkdir -p '$stage/source/sketch'"
if ($LASTEXITCODE -ne 0) { throw "Could not create the deployment staging directory." }
foreach ($relative in $requiredFiles) {
    $local = Join-Path $trackedRoot $relative.Replace("/", [IO.Path]::DirectorySeparatorChar)
    & $AdbPath -s $DeviceSerial push $local "$stage/source/$relative"
    if ($LASTEXITCODE -ne 0) { throw "Could not upload $relative" }
}
& $AdbPath -s $DeviceSerial push $frameHeader "$stage/source/sketch/lightweave_optical_frame.h"
if ($LASTEXITCODE -ne 0) { throw "Could not upload the LWF1 sketch header." }
& $AdbPath -s $DeviceSerial push $parallelHeader "$stage/source/sketch/lightweave_parallel_optical.h"
if ($LASTEXITCODE -ne 0) { throw "Could not upload the parallel sketch header." }

$installCommand = @"
set -eu
mkdir -p '$targetApp/sketch'
install -m 0644 '$stage/source/app.yaml' '$targetApp/app.yaml'
install -m 0644 '$stage/source/README.md' '$targetApp/README.md'
install -m 0644 '$stage/source/parallel_receiver.manifest.json' '$targetApp/parallel_receiver.manifest.json'
install -m 0644 '$stage/source/sketch/sketch.ino' '$targetApp/sketch/sketch.ino'
install -m 0644 '$stage/source/sketch/sketch.yaml' '$targetApp/sketch/sketch.yaml'
install -m 0644 '$stage/source/sketch/lightweave_optical_frame.h' '$targetApp/sketch/lightweave_optical_frame.h'
install -m 0644 '$stage/source/sketch/lightweave_parallel_optical.h' '$targetApp/sketch/lightweave_parallel_optical.h'
find '$stage/source' -type f -delete
rmdir '$stage/source/sketch' '$stage/source' '$stage'
"@
& $AdbPath -s $DeviceSerial shell $installCommand
if ($LASTEXITCODE -ne 0) { throw "Could not install the parallel receiver overlay." }

$appListJson = (& $AdbPath -s $DeviceSerial shell "arduino-app-cli --format json app list") -join "`n"
if ($LASTEXITCODE -ne 0) { throw "Could not inspect App Lab applications." }
$appList = $appListJson | ConvertFrom-Json
$targetRunning = @($appList.apps | Where-Object { $_.name -eq $targetDisplayName -and $_.status -eq "running" }).Count -gt 0
if ($targetRunning) {
    & $AdbPath -s $DeviceSerial shell "arduino-app-cli app stop '$targetApp'"
    if ($LASTEXITCODE -ne 0) { throw "Could not stop the parallel receiver for its update." }
}
& $AdbPath -s $DeviceSerial shell "arduino-app-cli app clean-cache '$targetApp'"
if ($LASTEXITCODE -ne 0) { throw "Could not clear the parallel receiver cache." }

$sourceAfter = (& $AdbPath -s $DeviceSerial shell $hashCommand) -join "`n"
if ($LASTEXITCODE -ne 0 -or $sourceAfter -ne $sourceBefore) {
    throw "The standard receiver changed during installation."
}

if (-not $NoStart) {
    $appListJson = (& $AdbPath -s $DeviceSerial shell "arduino-app-cli --format json app list") -join "`n"
    $appList = $appListJson | ConvertFrom-Json
    $runningApps = @($appList.apps | Where-Object { $_.status -eq "running" -and $_.name -ne $targetDisplayName })
    if ($runningApps.Count -gt 0 -and -not $StopRunningApp) {
        throw "Another App Lab app is running ($($runningApps.name -join ', ')). Re-run with -StopRunningApp."
    }
    foreach ($runningApp in $runningApps) {
        $encoded = [string]$runningApp.id
        $padded = $encoded.Replace("-", "+").Replace("_", "/")
        while ($padded.Length % 4) { $padded += "=" }
        $appId = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($padded))
        & $AdbPath -s $DeviceSerial shell "arduino-app-cli app stop '$appId'"
        if ($LASTEXITCODE -ne 0) { throw "Could not stop $($runningApp.name)." }
    }
    & $AdbPath -s $DeviceSerial shell "arduino-app-cli app restart '$targetApp'"
    if ($LASTEXITCODE -ne 0) { throw "Could not start the parallel receiver." }
}

Write-Host "Standard receiver hashes are unchanged."
Write-Host "Parallel receiver installation completed."
