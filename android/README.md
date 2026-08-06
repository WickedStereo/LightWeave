# LightWeave Android receiver

This Android Studio project is the phone-facing receiver for decoded
LightWeave results. The intended boundary is:

```text
optical receiver -> UNO Q receives and reconstructs -> USB-C -> Android app
```

The app does not run the LightWeave AI decoder. It receives standard output
from the UNO Q and currently supports:

- UTF-8 text;
- PNG or JPEG images;
- automatic matching of the locally observed UNO Q USB identity `2341:0078`;
- Android USB-host attach, detach, and permission handling;
- CDC/ACM reads through `usb-serial-for-android` 3.10.0;
- incremental frame parsing across arbitrary USB read boundaries;
- CRC32 validation and stream resynchronization; and
- local text/image demos that do not require hardware.

Audio is intentionally deferred. The UNO Q decoder now passes independently;
UNO Q-to-Galaxy enumeration, sustained power, USB interface layout, and
decoded-result delivery remain hardware validation gates.

## Open in Android Studio

1. Install a current Android Studio build if it is not already installed.
2. Select **File > Open**.
3. Open the `LightWeave/android` directory, not the repository root.
4. Use the bundled JDK 17 and allow the initial Gradle sync to download the
   pinned USB-serial dependency.
5. Select the `app` run configuration.

The project targets Android API 36, has a minimum API of 26, and does not
request Internet or broad storage permission.

Because the S25 USB-C port will be occupied by the UNO Q, use Android Studio's
[wireless debugging](https://developer.android.com/studio/run/device#wireless)
when debugging the real link. Pair the phone first, then connect the UNO Q.

## Build from PowerShell

```powershell
cd android
$env:ANDROID_HOME="$env:LOCALAPPDATA\Android\Sdk"
.\gradlew.bat lintDebug testDebugUnitTest assembleDebug
```

The ignored development APK is written to:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

## Work without the UNO Q

Run the app and select **Demo text** or **Demo image**. These buttons generate
real `LWRX` frames, pass them through the same incremental parser used by USB,
and render the resulting content. They validate the phone application flow,
not the physical cable or board.

## UNO Q-to-phone frame format

USB framing is separate from the low-bandwidth optical payload. It is added
only after the UNO Q has reconstructed the result, so it does not count
against the optical byte budget.

All integer fields are little-endian:

| Offset | Size | Field |
| ---: | ---: | --- |
| 0 | 4 | ASCII magic `LWRX` |
| 4 | 1 | Version `1` |
| 5 | 1 | Type: `1` UTF-8 text, `2` PNG/JPEG image |
| 6 | 2 | Flags, currently `0` |
| 8 | 4 | Payload byte length |
| 12 | 4 | CRC32 of payload |
| 16 | N | Payload bytes |

The app rejects unknown versions, media types, flags, CRC failures, malformed
UTF-8, unsupported images, payloads larger than 8 MiB, and images larger than
16 megapixels.

A future UNO Q Linux sender can construct a frame like this:

```python
import struct
import zlib

TYPE_TEXT = 1
TYPE_IMAGE = 2


def lightweave_frame(media_type: int, payload: bytes) -> bytes:
    header = struct.pack(
        "<4sBBHII",
        b"LWRX",
        1,
        media_type,
        0,
        len(payload),
        zlib.crc32(payload) & 0xFFFFFFFF,
    )
    return header + payload
```

Write the returned bytes to the UNO Q's validated phone-facing CDC stream.
The exact UNO Q device node or Bridge route must be discovered on the board;
it is intentionally not guessed here.
