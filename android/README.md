# LightWeave Mobile

LightWeave Mobile is the standalone display and control application for the
production **LightWeave Receiver** on Arduino UNO Q. The final receiver-side
demo needs only the Galaxy S25 Ultra and the receiver UNO Q:

```text
laser -> UNO Q validates LWF1 -> UNO Q reconstructs -> USB-C -> Galaxy app
                                  ^                         |
                                  +---- Listen/Cancel ------+
```

The phone does not run an AI model. The UNO Q retains the working text path,
strict Adreno image decoder, and CPU/Adreno audio decoder. The app replaces the
board-hosted webpage as the presentation surface and provides:

- USB **Listen for transfer**, **Cancel**, and current-status commands;
- decoded printable text;
- exact reconstructed PNG display and save;
- reconstructed WAV playback and save;
- the parsed optical profile, size, CRC, stop bit, timings, model evidence,
  QRB2210 CPU stages, Adreno 702 stages, and STM32 work;
- a persistent plain light/dark mode; and
- fully offline runtime with no Android Internet or broad-storage permission.

The repository tag `lightweave-pre-android-rebuild` preserves the complete
working receiver baseline from before this fresh mobile project.

## One-time Android setup

The laptop is required to build and install the app, but it is not present in
the final runtime display.

1. Install Android Studio with Android SDK Platform 36 and JDK 17.
2. Open the repository's `android` directory as the Android Studio project.
3. Allow the first Gradle sync to download the pinned USB serial dependency.
4. Enable Developer options and wireless debugging on the Galaxy S25 Ultra.
5. Install the `app` debug or signed release build while the phone is available
   to Android Studio. Wireless debugging is useful because the phone USB-C port
   will be occupied by UNO Q during the demo.

PowerShell build verification:

```powershell
cd android
$env:ANDROID_HOME="$env:LOCALAPPDATA\Android\Sdk"
.\gradlew.bat clean lintDebug testDebugUnitTest assembleDebug
```

The ignored development APK is produced at
`android/app/build/outputs/apk/debug/app-debug.apk`.

## Prepare the receiver UNO Q

Install the accelerated receiver artifacts first, then the production App Lab
receiver and its narrow USB-device permission:

```powershell
.\scripts\install_uno_q.ps1 -DeviceSerial <RX_SERIAL> -DryRun
.\scripts\install_uno_q_optical_receiver.ps1 `
  -DeviceSerial <RX_SERIAL> -DryRun
.\scripts\install_uno_q_optical_receiver.ps1 `
  -DeviceSerial <RX_SERIAL> -StopRunningApp
```

The installer keeps the original `image_receiver`, `laser_receiver_ui`, and
`lightweave_optical_receiver` source unchanged. It grants only the running
LightWeave Receiver service access to `/dev/ttyGS0`; it does not modify the
base OS or transmitter.

## Standalone runtime

1. Ensure **LightWeave Receiver** is already running on the receiver UNO Q.
2. Open LightWeave Mobile on the S25 Ultra.
3. Connect the receiver UNO Q directly to the phone with a data-capable USB-C
   cable. Grant the Android USB permission prompt.
4. If the phone cannot power UNO Q reliably, place a USB-C OTG/PD hub that can
   power the board between them; the phone must remain USB host and UNO Q USB
   device.
5. Tap **Listen for transfer** in the phone app.
6. Trigger the existing transmitter. No laptop is required on the receiver
   side. After validation and reconstruction, the result and evidence arrive
   automatically in the phone app.
7. For audio, tap **Play audio**. Use **Save result** for TXT, PNG, or WAV.

## USB contracts

Phone-to-board control uses fixed 12-byte `LWCT/1` frames: magic `LWCT`, version
1, command (`1` listen, `2` cancel, `3` status), zero flags, and little-endian
CRC32 over the first eight bytes.

Board-to-phone results use `LWRX/2`:

| Offset | Size | Field |
| ---: | ---: | --- |
| 0 | 4 | Magic `LWRX` |
| 4 | 1 | Version `2` |
| 5 | 1 | Type: text `1`, PNG `2`, WAV `3`, status `4` |
| 6 | 2 | Flags, zero |
| 8 | 4 | UTF-8 JSON metadata length, little-endian |
| 12 | 4 | decoded media length, little-endian |
| 16 | 4 | CRC32, little-endian |
| 20 | M | metadata JSON |
| 20+M | N | decoded TXT/PNG/WAV or status JSON |

The CRC covers the 16-byte prefix, metadata, and media, but excludes the stored
CRC field. The receiver persists completed result frames in an outbox until a
phone opens USB, so a brief disconnect does not discard decoded media.

This downstream USB frame never travels over the laser and does not change the
minimal optical payload or `LWF1` transmitter protocol.

## Verification boundary

The Android parser, controls, lint, unit tests, and APK build are verified on
the Snapdragon Windows development system. UNO Q-to-Windows CDC delivery was
also verified byte-for-byte through `/dev/ttyGS0`. The final remaining hardware
gate is direct S25 enumeration, sustained board power, and an end-to-end
text/image/audio run while the phone owns the USB cable.
