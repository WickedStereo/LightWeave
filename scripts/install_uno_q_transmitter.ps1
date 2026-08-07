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
$sourceRoot = (Resolve-Path (Join-Path $projectRoot "uno_q\transmitter_app")).Path
$sourceApp = "/home/arduino/ArduinoApps/image_transmitter_bkp"
$targetApp = "/home/arduino/ArduinoApps/lightweave_transmitter"
$requiredFiles = @(
    "app.yaml",
    "README.md",
    "transmitter.manifest.json",
    "python/lightweave_transmitter.py",
    "python/main.py",
    "python/requirements.txt",
    "sketch/sketch.ino",
    "sketch/sketch.yaml"
)

foreach ($relative in $requiredFiles) {
    $local = Join-Path $sourceRoot $relative.Replace("/", [IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path -LiteralPath $local -PathType Leaf)) {
        throw "Tracked transmitter source is missing: $relative"
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
    $authorized = @(
        (& $AdbPath devices) |
            Select-String '\sdevice$' |
            ForEach-Object { ($_ -split '\s+')[0] }
    )
    $connected = @(
        foreach ($candidateSerial in $authorized) {
            & $AdbPath -s $candidateSerial shell "command -v arduino-app-cli >/dev/null 2>&1"
            if ($LASTEXITCODE -eq 0) { $candidateSerial }
        }
    )
    if ($connected.Count -ne 1) {
        throw "Expected exactly one connected UNO Q; pass -DeviceSerial."
    }
    $DeviceSerial = $connected[0]
}

$doctor = & $AdbPath -s $DeviceSerial shell "printf 'ARCH='; uname -m; printf '\nAPP_CLI='; arduino-app-cli version 2>/dev/null | head -1; printf '\nFREE_KB='; df -Pk /home/arduino | awk 'NR==2 {print `$4}'"
if ($LASTEXITCODE -ne 0) { throw "Could not inspect the UNO Q." }
$doctorText = $doctor -join "`n"
if ($doctorText -notmatch 'ARCH=aarch64') { throw "Target is not Linux ARM64." }
if ($doctorText -notmatch 'APP_CLI=Arduino App CLI version') {
    throw "Arduino App CLI is unavailable."
}
$freeMatch = [regex]::Match($doctorText, 'FREE_KB=(\d+)')
if (-not $freeMatch.Success -or [int64]$freeMatch.Groups[1].Value -lt 65536) {
    throw "UNO Q has less than 64 MiB free disk space."
}

$backupHashCommand = "cd '$sourceApp' && sha256sum app.yaml python/main.py sketch/sketch.ino"
$backupBefore = (& $AdbPath -s $DeviceSerial shell $backupHashCommand) -join "`n"
if ($LASTEXITCODE -ne 0 -or ($backupBefore -split "`n").Count -ne 3) {
    throw "Could not hash the image_transmitter_bkp source."
}

$targetProbe = & $AdbPath -s $DeviceSerial shell "test -d '$targetApp'"
$targetExists = $LASTEXITCODE -eq 0
if ($targetExists) {
    & $AdbPath -s $DeviceSerial shell "test -f '$targetApp/transmitter.manifest.json'"
    if ($LASTEXITCODE -ne 0) {
        throw "Refusing to overwrite an unrelated lightweave_transmitter app."
    }
}

Write-Host "Source app: image_transmitter_bkp (read-only)"
Write-Host "Target app: lightweave_transmitter"
Write-Host "Tracked source: $sourceRoot"
Write-Host "Backup source hashes recorded: 3"
if ($DryRun) {
    Write-Host "Dry run passed; the board was not modified."
    exit 0
}

if (-not $targetExists) {
    & $AdbPath -s $DeviceSerial shell "arduino-app-cli app new lightweave_transmitter --from-app '$sourceApp'"
    if ($LASTEXITCODE -ne 0) { throw "Could not clone image_transmitter_bkp." }
}

$stage = "/tmp/lightweave-transmitter-$([guid]::NewGuid().ToString('N').Substring(0, 10))"
& $AdbPath -s $DeviceSerial shell "mkdir -p '$stage/source/python' '$stage/source/sketch'"
if ($LASTEXITCODE -ne 0) { throw "Could not create the deployment staging directory." }
foreach ($relative in $requiredFiles) {
    $local = Join-Path $sourceRoot $relative.Replace("/", [IO.Path]::DirectorySeparatorChar)
    $remote = "$stage/source/$relative"
    & $AdbPath -s $DeviceSerial push $local $remote
    if ($LASTEXITCODE -ne 0) {
        throw "Could not upload tracked transmitter source: $relative"
    }
}

$installCommand = @"
set -eu
mkdir -p '$targetApp/python' '$targetApp/sketch' '$targetApp/data/inbox' '$targetApp/data/processing' '$targetApp/data/results'
install -m 0644 '$stage/source/app.yaml' '$targetApp/app.yaml'
install -m 0644 '$stage/source/README.md' '$targetApp/README.md'
install -m 0644 '$stage/source/transmitter.manifest.json' '$targetApp/transmitter.manifest.json'
install -m 0644 '$stage/source/python/lightweave_transmitter.py' '$targetApp/python/lightweave_transmitter.py'
install -m 0644 '$stage/source/python/main.py' '$targetApp/python/main.py'
install -m 0644 '$stage/source/python/requirements.txt' '$targetApp/python/requirements.txt'
install -m 0644 '$stage/source/sketch/sketch.ino' '$targetApp/sketch/sketch.ino'
install -m 0644 '$stage/source/sketch/sketch.yaml' '$targetApp/sketch/sketch.yaml'
rm -f '$targetApp/python/image.jpg' '$targetApp/python/images.jpg'
rm -f '$stage/source/python/lightweave_transmitter.py' '$stage/source/python/main.py' '$stage/source/python/requirements.txt'
rm -f '$stage/source/sketch/sketch.ino' '$stage/source/sketch/sketch.yaml'
rm -f '$stage/source/app.yaml' '$stage/source/README.md' '$stage/source/transmitter.manifest.json'
rmdir '$stage/source/python' '$stage/source/sketch' '$stage/source' '$stage'
"@
& $AdbPath -s $DeviceSerial shell $installCommand
if ($LASTEXITCODE -ne 0) { throw "Could not install tracked transmitter files." }

$targetListJson = (& $AdbPath -s $DeviceSerial shell "arduino-app-cli --format json app list") -join "`n"
if ($LASTEXITCODE -ne 0) { throw "Could not inspect the transmitter app state." }
$targetList = $targetListJson | ConvertFrom-Json
$targetRunning = @(
    $targetList.apps |
        Where-Object {
            $_.name -eq "lightweave_transmitter" -and $_.status -eq "running"
        }
).Count -gt 0
if ($targetRunning) {
    & $AdbPath -s $DeviceSerial shell "arduino-app-cli app stop '$targetApp'"
    if ($LASTEXITCODE -ne 0) { throw "Could not stop the running transmitter for its update." }
}

& $AdbPath -s $DeviceSerial shell "arduino-app-cli app clean-cache '$targetApp'"
if ($LASTEXITCODE -ne 0) { throw "Could not clear the cloned app cache." }

$backupAfter = (& $AdbPath -s $DeviceSerial shell $backupHashCommand) -join "`n"
if ($LASTEXITCODE -ne 0 -or $backupAfter -ne $backupBefore) {
    throw "image_transmitter_bkp changed during installation. Stop and inspect the board."
}

if (-not $NoStart) {
    $appListJson = (& $AdbPath -s $DeviceSerial shell "arduino-app-cli --format json app list") -join "`n"
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect running App Lab applications." }
    $appList = $appListJson | ConvertFrom-Json
    $runningApps = @(
        $appList.apps |
            Where-Object {
                $_.status -eq "running" -and $_.name -ne "lightweave_transmitter"
            }
    )
    if ($runningApps.Count -gt 0 -and -not $StopRunningApp) {
        $names = ($runningApps.name -join ", ")
        throw "Another App Lab app is running ($names). Re-run with -StopRunningApp to stop it first."
    }
    foreach ($runningApp in $runningApps) {
        $encoded = [string]$runningApp.id
        $padded = $encoded.Replace("-", "+").Replace("_", "/")
        while ($padded.Length % 4) { $padded += "=" }
        $appId = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($padded))
        & $AdbPath -s $DeviceSerial shell "arduino-app-cli app stop '$appId'"
        if ($LASTEXITCODE -ne 0) { throw "Could not stop running App Lab app: $($runningApp.name)" }
        Write-Host "Stopped App Lab app: $($runningApp.name)"
    }
    & $AdbPath -s $DeviceSerial shell "arduino-app-cli app restart '$targetApp'"
    if ($LASTEXITCODE -ne 0) { throw "App Lab could not start lightweave_transmitter." }
}

Write-Host "Backup hashes unchanged."
Write-Host "LightWeave transmitter installation completed."
