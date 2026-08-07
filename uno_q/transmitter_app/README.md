# LightWeave UNO Q transmitter

This App Lab project is derived from the owner's `image_transmitter_bkp`
application. The installer hashes that backup before and after deployment and
updates only the tracked `lightweave_transmitter` clone.

The Windows dashboard places the unchanged `payload.bin` in an atomic ADB
inbox. The Linux worker validates request schema 2, SHA-256, profile, media
parameter, and payload budget, then loads the exact raw bytes into the STM32
through RouterBridge. By default the STM32 emits an `LWF1` optical frame:

1. one high start bit;
2. the ten-byte `LW`/version/profile/length/media-parameter header;
3. the raw payload, unchanged and MSB first;
4. CRC-16/CCITT-FALSE as two little-endian bytes;
5. one low stop bit.

Pin 9 and 25 milliseconds per bit are unchanged. `raw-v0` is retained only for
the explicit byte-receiver diagnostic. It emits the old start/payload/stop
waveform without the LWF1 header or CRC.

From the repository root, inspect and install with:

```powershell
.\scripts\install_uno_q_transmitter.ps1 -DeviceSerial <TX_SERIAL> -DryRun
.\scripts\install_uno_q_transmitter.ps1 -DeviceSerial <TX_SERIAL> -StopRunningApp
```

The dashboard uses ADB over USB and requires no network connection. Generated
`payload.bin` files remain raw codec payloads; framing is produced only by the
STM32 while transmitting.
