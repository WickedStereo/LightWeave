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
$trackedRoot = (Resolve-Path (Join-Path $projectRoot "uno_q\byte_receiver_app")).Path
$sourceApp = "/home/arduino/ArduinoApps/laser_receiver_ui"
$logicSourceApp = "/home/arduino/ArduinoApps/image_receiver"
$targetApp = "/home/arduino/ArduinoApps/lightweave_byte_receiver"
$requiredFiles = @(
    "app.yaml",
    "README.md",
    "byte_receiver.manifest.json",
    "assets/index.html",
    "assets/app.js",
    "assets/style.css",
    "python/lightweave_byte_receiver.py",
    "python/main.py",
    "python/requirements.txt",
    "sketch/sketch.ino",
    "sketch/sketch.yaml"
)

foreach ($relative in $requiredFiles) {
    $local = Join-Path $trackedRoot $relative.Replace("/", [IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path -LiteralPath $local -PathType Leaf)) {
        throw "Tracked byte-receiver source is missing: $relative"
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
    throw "Pass -DeviceSerial or set LIGHTWEAVE_UNO_Q_RECEIVER_SERIAL. Auto-selection is disabled when two UNO Q boards are expected."
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
$freeMatch = [regex]::Match($doctorText, 'FREE_KB=(\d+)')
if (-not $freeMatch.Success -or [int64]$freeMatch.Groups[1].Value -lt 65536) {
    throw "Receiver UNO Q has less than 64 MiB free disk space."
}

$sourceHashCommand = "cd '$sourceApp' && sha256sum app.yaml python/main.py sketch/sketch.ino assets/libs/socket.io.min.js; cd '$logicSourceApp' && sha256sum app.yaml python/main.py sketch/sketch.ino"
$sourceBefore = (& $AdbPath -s $DeviceSerial shell $sourceHashCommand) -join "`n"
if ($LASTEXITCODE -ne 0 -or ($sourceBefore -split "`n").Count -ne 7) {
    throw "Could not hash the existing receiver sources."
}

& $AdbPath -s $DeviceSerial shell "test -d '$targetApp'"
$targetExists = $LASTEXITCODE -eq 0
if ($targetExists) {
    & $AdbPath -s $DeviceSerial shell "test -f '$targetApp/byte_receiver.manifest.json'"
    if ($LASTEXITCODE -ne 0) {
        throw "Refusing to overwrite an unrelated lightweave_byte_receiver app."
    }
}

Write-Host "Receiver device: $DeviceSerial"
Write-Host "Receiver host: $(([regex]::Match($doctorText, 'HOST=([^\r\n]+)')).Groups[1].Value)"
Write-Host "Source apps: laser_receiver_ui and image_receiver (read-only)"
Write-Host "Target app: lightweave_byte_receiver"
Write-Host "Tracked source: $trackedRoot"
if ($DryRun) {
    Write-Host "Dry run passed; neither board was modified."
    exit 0
}

if (-not $targetExists) {
    & $AdbPath -s $DeviceSerial shell "arduino-app-cli app new lightweave_byte_receiver --from-app '$sourceApp'"
    if ($LASTEXITCODE -ne 0) { throw "Could not clone laser_receiver_ui." }
}

$stage = "/tmp/lightweave-byte-rx-$([guid]::NewGuid().ToString('N').Substring(0, 10))"
& $AdbPath -s $DeviceSerial shell "mkdir -p '$stage/source/assets' '$stage/source/python' '$stage/source/sketch'"
if ($LASTEXITCODE -ne 0) { throw "Could not create receiver staging directories." }
foreach ($relative in $requiredFiles) {
    $local = Join-Path $trackedRoot $relative.Replace("/", [IO.Path]::DirectorySeparatorChar)
    $remote = "$stage/source/$relative"
    & $AdbPath -s $DeviceSerial push $local $remote
    if ($LASTEXITCODE -ne 0) {
        throw "Could not upload tracked byte-receiver source: $relative"
    }
}

$installCommand = @"
set -eu
mkdir -p '$targetApp/assets' '$targetApp/python' '$targetApp/sketch' '$targetApp/data/inbox' '$targetApp/data/processing' '$targetApp/data/results'
install -m 0644 '$stage/source/app.yaml' '$targetApp/app.yaml'
install -m 0644 '$stage/source/README.md' '$targetApp/README.md'
install -m 0644 '$stage/source/byte_receiver.manifest.json' '$targetApp/byte_receiver.manifest.json'
install -m 0644 '$stage/source/assets/index.html' '$targetApp/assets/index.html'
install -m 0644 '$stage/source/assets/app.js' '$targetApp/assets/app.js'
install -m 0644 '$stage/source/assets/style.css' '$targetApp/assets/style.css'
install -m 0644 '$stage/source/python/lightweave_byte_receiver.py' '$targetApp/python/lightweave_byte_receiver.py'
install -m 0644 '$stage/source/python/main.py' '$targetApp/python/main.py'
install -m 0644 '$stage/source/python/requirements.txt' '$targetApp/python/requirements.txt'
install -m 0644 '$stage/source/sketch/sketch.ino' '$targetApp/sketch/sketch.ino'
install -m 0644 '$stage/source/sketch/sketch.yaml' '$targetApp/sketch/sketch.yaml'
find '$stage/source' -type f -delete
rmdir '$stage/source/assets' '$stage/source/python' '$stage/source/sketch' '$stage/source' '$stage'
"@
& $AdbPath -s $DeviceSerial shell $installCommand
if ($LASTEXITCODE -ne 0) { throw "Could not install tracked byte-receiver files." }

$targetListJson = (& $AdbPath -s $DeviceSerial shell "arduino-app-cli --format json app list") -join "`n"
if ($LASTEXITCODE -ne 0) { throw "Could not inspect the byte-receiver app state." }
$targetList = $targetListJson | ConvertFrom-Json
$targetRunning = @(
    $targetList.apps |
        Where-Object {
            $_.name -eq "lightweave_byte_receiver" -and $_.status -eq "running"
        }
).Count -gt 0
if ($targetRunning) {
    & $AdbPath -s $DeviceSerial shell "arduino-app-cli app stop '$targetApp'"
    if ($LASTEXITCODE -ne 0) { throw "Could not stop the running byte receiver for its update." }
}

& $AdbPath -s $DeviceSerial shell "arduino-app-cli app clean-cache '$targetApp'"
if ($LASTEXITCODE -ne 0) { throw "Could not clear the byte-receiver cache." }

$sourceAfter = (& $AdbPath -s $DeviceSerial shell $sourceHashCommand) -join "`n"
if ($LASTEXITCODE -ne 0 -or $sourceAfter -ne $sourceBefore) {
    throw "An existing receiver app changed during installation. Stop and inspect the board."
}

if (-not $NoStart) {
    $appListJson = (& $AdbPath -s $DeviceSerial shell "arduino-app-cli --format json app list") -join "`n"
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect receiver App Lab state." }
    $appList = $appListJson | ConvertFrom-Json
    $runningApps = @(
        $appList.apps |
            Where-Object {
                $_.status -eq "running" -and $_.name -ne "lightweave_byte_receiver"
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
    }
    & $AdbPath -s $DeviceSerial shell "arduino-app-cli app restart '$targetApp'"
    if ($LASTEXITCODE -ne 0) { throw "App Lab could not start lightweave_byte_receiver." }
}

Write-Host "Existing receiver hashes are unchanged."
Write-Host "LightWeave byte-receiver installation completed."
