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
$trackedRoot = (Resolve-Path (Join-Path $projectRoot "uno_q\optical_receiver_app")).Path
$framePython = (Resolve-Path (Join-Path $projectRoot "src\lightweave\optical_frame.py")).Path
$frameHeader = (Resolve-Path (Join-Path $projectRoot "uno_q\common\lightweave_optical_frame.h")).Path
$noticePath = (Resolve-Path (Join-Path $projectRoot "uno_q\native\THIRD_PARTY_NOTICES.md")).Path
$decoderSource = "/home/arduino/ArduinoApps/lightweave-uno"
$receiverSource = "/home/arduino/ArduinoApps/image_receiver"
$uiSource = "/home/arduino/ArduinoApps/laser_receiver_ui"
$rollbackSource = "/home/arduino/ArduinoApps/lightweave_optical_receiver"
$targetApp = "/home/arduino/ArduinoApps/lightweave_receiver"
$targetDisplayName = "LightWeave Receiver"
$requiredFiles = @(
    "app.yaml",
    "README.md",
    "optical_receiver.manifest.json",
    "assets/index.html",
    "assets/app.js",
    "assets/style.css",
    "python/lightweave_optical_receiver.py",
    "python/main.py",
    "python/phone_usb.py",
    "python/requirements.txt",
    "sketch/sketch.ino",
    "sketch/sketch.yaml"
)

foreach ($relative in $requiredFiles) {
    $local = Join-Path $trackedRoot $relative.Replace("/", [IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path -LiteralPath $local -PathType Leaf)) {
        throw "Tracked optical-receiver source is missing: $relative"
    }
}
if (-not (Test-Path -LiteralPath $noticePath -PathType Leaf)) {
    throw "Tracked UNO Q third-party notice is missing."
}
foreach ($shared in @($framePython, $frameHeader)) {
    if (-not (Test-Path -LiteralPath $shared -PathType Leaf)) {
        throw "Shared LWF1 protocol source is missing: $shared"
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

if (-not $DeviceSerial) {
    $DeviceSerial = $env:LIGHTWEAVE_UNO_Q_RECEIVER_SERIAL
}
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

$doctor = & $AdbPath -s $DeviceSerial shell "printf 'ARCH='; uname -m; printf '\nHOST='; hostname; printf '\nAPP_CLI='; arduino-app-cli version 2>/dev/null | head -1; printf '\nFREE_KB='; df -Pk /home/arduino | awk 'NR==2 {print `$4}'"
if ($LASTEXITCODE -ne 0) { throw "Could not inspect the receiver UNO Q." }
$doctorText = $doctor -join "`n"
if ($doctorText -notmatch 'ARCH=aarch64') { throw "Target is not Linux ARM64." }
if ($doctorText -notmatch 'APP_CLI=Arduino App CLI version') {
    throw "Arduino App CLI is unavailable."
}
& $AdbPath -s $DeviceSerial shell "test -c /dev/ttyGS0"
if ($LASTEXITCODE -ne 0) {
    throw "Receiver UNO Q does not expose the expected /dev/ttyGS0 USB CDC gadget."
}
& $AdbPath -s $DeviceSerial shell "systemctl is-active --quiet arduino-router arduino-router-serial && systemctl is-enabled --quiet arduino-router-serial"
if ($LASTEXITCODE -ne 0) {
    throw "UNO Q's boot-managed Arduino Router serial bridge is unavailable."
}
$freeMatch = [regex]::Match($doctorText, 'FREE_KB=(\d+)')
if (-not $freeMatch.Success -or [int64]$freeMatch.Groups[1].Value -lt 131072) {
    throw "Receiver UNO Q has less than 128 MiB free disk space."
}

$requiredBoardFiles = @(
    "$decoderSource/app.yaml",
    "$decoderSource/python/lightweave_uno.py",
    "$decoderSource/uno_q.manifest.json",
    "$decoderSource/runtime/lightweave-uno-runner",
    "$decoderSource/runtime/entropy_tables.bin",
    "$decoderSource/runtime/tiny.ncnn.param",
    "$decoderSource/runtime/tiny.ncnn.bin",
    "$decoderSource/runtime/balanced.ncnn.param",
    "$decoderSource/runtime/balanced.ncnn.bin",
    "$decoderSource/runtime/quality.ncnn.param",
    "$decoderSource/runtime/quality.ncnn.bin",
    "$decoderSource/runtime/audio-codebooks.bin",
    "$decoderSource/runtime/audio-prefix.ncnn.bin",
    "$decoderSource/runtime/audio-prefix-1s.ncnn.param",
    "$decoderSource/runtime/audio-prefix-2s.ncnn.param",
    "$decoderSource/runtime/audio-prefix-3s.ncnn.param",
    "$decoderSource/runtime/audio-prefix-4s.ncnn.param",
    "$decoderSource/runtime/audio-prefix-5s.ncnn.param",
    "$decoderSource/runtime/audio-tail.ncnn.param",
    "$decoderSource/runtime/audio-tail.ncnn.bin",
    "$receiverSource/sketch/sketch.ino",
    "$uiSource/app.yaml",
    "$uiSource/python/main.py",
    "$uiSource/sketch/sketch.ino",
    "$uiSource/assets/libs/socket.io.min.js"
)
foreach ($remote in $requiredBoardFiles) {
    & $AdbPath -s $DeviceSerial shell "test -f '$remote'"
    if ($LASTEXITCODE -ne 0) { throw "Required receiver component is missing: $remote" }
}

$trackedDecoderHash = (Get-FileHash -LiteralPath (Join-Path $projectRoot "uno_q\app\python\lightweave_uno.py") -Algorithm SHA256).Hash.ToLowerInvariant()
$boardDecoderHash = ((& $AdbPath -s $DeviceSerial shell "sha256sum '$decoderSource/python/lightweave_uno.py' | cut -d' ' -f1") -join "").Trim()
if ($LASTEXITCODE -ne 0 -or $boardDecoderHash -ne $trackedDecoderHash) {
    throw "The installed LightWeave decoder source does not match this repository. Reinstall the base UNO Q bundle first."
}

$rollbackHashSuffix = ""
& $AdbPath -s $DeviceSerial shell "test -d '$rollbackSource'"
$rollbackExists = $LASTEXITCODE -eq 0
if ($rollbackExists) {
    $rollbackHashSuffix = " '$rollbackSource/app.yaml' '$rollbackSource/python/lightweave_optical_receiver.py' '$rollbackSource/sketch/sketch.ino'"
}
$sourceHashCommand = "sha256sum '$decoderSource/app.yaml' '$decoderSource/python/lightweave_uno.py' '$decoderSource/uno_q.manifest.json' '$decoderSource/runtime/lightweave-uno-runner' '$decoderSource/runtime/entropy_tables.bin' '$decoderSource/runtime/tiny.ncnn.param' '$decoderSource/runtime/tiny.ncnn.bin' '$decoderSource/runtime/balanced.ncnn.param' '$decoderSource/runtime/balanced.ncnn.bin' '$decoderSource/runtime/quality.ncnn.param' '$decoderSource/runtime/quality.ncnn.bin' '$receiverSource/app.yaml' '$receiverSource/python/main.py' '$receiverSource/sketch/sketch.ino' '$uiSource/app.yaml' '$uiSource/python/main.py' '$uiSource/sketch/sketch.ino' '$uiSource/assets/libs/socket.io.min.js'$rollbackHashSuffix"
$sourceBefore = (& $AdbPath -s $DeviceSerial shell $sourceHashCommand) -join "`n"
if ($LASTEXITCODE -ne 0 -or -not $sourceBefore) {
    throw "Could not hash the reusable receiver components."
}

& $AdbPath -s $DeviceSerial shell "test -d '$targetApp'"
$targetExists = $LASTEXITCODE -eq 0
if ($targetExists) {
    & $AdbPath -s $DeviceSerial shell "test -f '$targetApp/optical_receiver.manifest.json'"
    if ($LASTEXITCODE -ne 0) {
        throw "Refusing to overwrite an unrelated lightweave_receiver app."
    }
}

Write-Host "Receiver device: $DeviceSerial"
Write-Host "Receiver host: $(([regex]::Match($doctorText, 'HOST=([^\r\n]+)')).Groups[1].Value)"
Write-Host "Decoder source: lightweave-uno (read-only)"
Write-Host "Optical source: image_receiver (read-only)"
Write-Host "Legacy text source: laser_receiver_ui (read-only)"
Write-Host "Rollback receiver: lightweave_optical_receiver ($(if ($rollbackExists) { 'read-only' } else { 'not installed' }))"
Write-Host "Target app: lightweave_receiver / $targetDisplayName"
Write-Host "Tracked source: $trackedRoot"
if ($DryRun) {
    Write-Host "Dry run passed; the receiver board was not modified."
    exit 0
}

if (-not $targetExists) {
    & $AdbPath -s $DeviceSerial shell "arduino-app-cli app new lightweave_receiver --from-app '$decoderSource'"
    if ($LASTEXITCODE -ne 0) { throw "Could not clone the installed LightWeave receiver." }
}

$stage = "/tmp/lightweave-optical-rx-$([guid]::NewGuid().ToString('N').Substring(0, 10))"
& $AdbPath -s $DeviceSerial shell "mkdir -p '$stage/source/assets' '$stage/source/python' '$stage/source/sketch'"
if ($LASTEXITCODE -ne 0) { throw "Could not create receiver staging directories." }
foreach ($relative in $requiredFiles) {
    $local = Join-Path $trackedRoot $relative.Replace("/", [IO.Path]::DirectorySeparatorChar)
    & $AdbPath -s $DeviceSerial push $local "$stage/source/$relative"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not upload tracked optical-receiver source: $relative"
    }
}
& $AdbPath -s $DeviceSerial push $framePython "$stage/source/python/lightweave_optical_frame.py"
if ($LASTEXITCODE -ne 0) { throw "Could not upload the shared LWF1 Python contract." }
& $AdbPath -s $DeviceSerial push $frameHeader "$stage/source/sketch/lightweave_optical_frame.h"
if ($LASTEXITCODE -ne 0) { throw "Could not upload the shared LWF1 C++ contract." }
& $AdbPath -s $DeviceSerial push $noticePath "$stage/source/THIRD_PARTY_NOTICES.md"
if ($LASTEXITCODE -ne 0) { throw "Could not upload the UNO Q third-party notice." }

$installCommand = @"
set -eu
mkdir -p '$targetApp/assets/libs' '$targetApp/python' '$targetApp/sketch' '$targetApp/data/inbox' '$targetApp/data/processing' '$targetApp/data/results' '$targetApp/data/phone-outbox'
install -m 0644 '$stage/source/app.yaml' '$targetApp/app.yaml'
install -m 0644 '$stage/source/README.md' '$targetApp/README.md'
install -m 0644 '$stage/source/optical_receiver.manifest.json' '$targetApp/optical_receiver.manifest.json'
install -m 0644 '$stage/source/THIRD_PARTY_NOTICES.md' '$targetApp/THIRD_PARTY_NOTICES.md'
install -m 0644 '$stage/source/assets/index.html' '$targetApp/assets/index.html'
install -m 0644 '$stage/source/assets/app.js' '$targetApp/assets/app.js'
install -m 0644 '$stage/source/assets/style.css' '$targetApp/assets/style.css'
install -m 0644 '$stage/source/python/lightweave_optical_receiver.py' '$targetApp/python/lightweave_optical_receiver.py'
install -m 0644 '$stage/source/python/main.py' '$targetApp/python/main.py'
install -m 0644 '$stage/source/python/phone_usb.py' '$targetApp/python/phone_usb.py'
install -m 0644 '$stage/source/python/requirements.txt' '$targetApp/python/requirements.txt'
install -m 0644 '$stage/source/python/lightweave_optical_frame.py' '$targetApp/python/lightweave_optical_frame.py'
install -m 0644 '$stage/source/sketch/sketch.ino' '$targetApp/sketch/sketch.ino'
install -m 0644 '$stage/source/sketch/sketch.yaml' '$targetApp/sketch/sketch.yaml'
install -m 0644 '$stage/source/sketch/lightweave_optical_frame.h' '$targetApp/sketch/lightweave_optical_frame.h'
install -m 0644 '$uiSource/assets/libs/socket.io.min.js' '$targetApp/assets/libs/socket.io.min.js'
test -x '$targetApp/runtime/lightweave-uno-runner'
test -f '$targetApp/uno_q.manifest.json'
rm -f '$targetApp/usb-compose.override.yaml'
find '$stage/source' -type f -delete
rmdir '$stage/source/assets' '$stage/source/python' '$stage/source/sketch' '$stage/source' '$stage'
"@
& $AdbPath -s $DeviceSerial shell $installCommand
if ($LASTEXITCODE -ne 0) { throw "Could not install tracked optical-receiver files." }

$targetListJson = (& $AdbPath -s $DeviceSerial shell "arduino-app-cli --format json app list") -join "`n"
if ($LASTEXITCODE -ne 0) { throw "Could not inspect the optical receiver state." }
$targetList = $targetListJson | ConvertFrom-Json
$targetRunning = @(
    $targetList.apps |
        Where-Object {
            $_.name -eq $targetDisplayName -and $_.status -eq "running"
        }
).Count -gt 0
if ($targetRunning) {
    & $AdbPath -s $DeviceSerial shell "arduino-app-cli app stop '$targetApp'"
    if ($LASTEXITCODE -ne 0) { throw "Could not stop the optical receiver for its update." }
}

& $AdbPath -s $DeviceSerial shell "arduino-app-cli app clean-cache '$targetApp'"
if ($LASTEXITCODE -ne 0) { throw "Could not clear the optical-receiver cache." }

$sourceAfter = (& $AdbPath -s $DeviceSerial shell $sourceHashCommand) -join "`n"
if ($LASTEXITCODE -ne 0 -or $sourceAfter -ne $sourceBefore) {
    throw "A reusable receiver source changed during installation. Stop and inspect the board."
}

if (-not $NoStart) {
    $appListJson = (& $AdbPath -s $DeviceSerial shell "arduino-app-cli --format json app list") -join "`n"
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect receiver App Lab state." }
    $appList = $appListJson | ConvertFrom-Json
    $runningApps = @(
        $appList.apps |
            Where-Object {
                $_.status -eq "running" -and $_.name -ne $targetDisplayName
            }
    )
    if ($runningApps.Count -gt 0 -and -not $StopRunningApp) {
        throw "Another receiver App Lab app is running: $($runningApps.name -join ', '). Re-run with -StopRunningApp only if it is safe to stop."
    }
    foreach ($runningApp in $runningApps) {
        $encoded = [string]$runningApp.id
        $padded = $encoded.Replace("-", "+").Replace("_", "/")
        while ($padded.Length % 4) { $padded += "=" }
        $appId = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($padded))
        & $AdbPath -s $DeviceSerial shell "arduino-app-cli app stop '$appId'"
        if ($LASTEXITCODE -ne 0) { throw "Could not stop receiver app: $($runningApp.name)" }
        Write-Host "Stopped App Lab app: $($runningApp.name)"
    }
    & $AdbPath -s $DeviceSerial shell "arduino-app-cli app restart '$targetApp'"
    if ($LASTEXITCODE -ne 0) { throw "App Lab could not start lightweave_receiver." }
    $routerProbePython = @'
from arduino.app_utils import Bridge

if Bridge.call("mon/connected", timeout=2) is not True:
    raise SystemExit("Arduino Router serial monitor is disconnected")
print("Arduino Router monitor bridge is connected")
'@
    $routerProbeBase64 = [Convert]::ToBase64String(
        [Text.Encoding]::UTF8.GetBytes($routerProbePython)
    )
    $routerProbeCommand = @'
set -eu
cd '__TARGET_APP__/.cache'
container=$(docker compose -f app-compose.yaml ps -q main)
test -n "$container"
printf %s '__PROBE_BASE64__' | base64 -d | docker exec -i "$container" python -
'@
    $routerProbeCommand = $routerProbeCommand.Replace('__TARGET_APP__', $targetApp)
    $routerProbeCommand = $routerProbeCommand.Replace('__PROBE_BASE64__', $routerProbeBase64)
    & $AdbPath -s $DeviceSerial shell $routerProbeCommand
    if ($LASTEXITCODE -ne 0) {
        throw "The receiver service could not access the Arduino Router monitor."
    }
}

Write-Host "Reusable source hashes are unchanged."
if (-not $NoStart) {
    Write-Host "Phone USB transport: boot-managed Arduino Router mon/read and mon/write."
}
Write-Host "LightWeave receiver installation completed."
