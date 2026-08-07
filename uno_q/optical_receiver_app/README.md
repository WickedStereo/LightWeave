# LightWeave UNO Q receiver

This App Lab project combines one-shot self-describing optical reception with
the installed native LightWeave image and audio decoders. It remains separate
from `lightweave_byte_receiver`, which is the unchanged `raw-v0` transport
diagnostic.

The production App Lab ID is `lightweave_receiver` and its display name is
**LightWeave Receiver**. Installation leaves the original
`laser_receiver_ui`, `image_receiver`, and former
`lightweave_optical_receiver` projects untouched.

The WebUI has a single **Listen for transfer** action and optional cancel. The
STM32 reads and validates the ten-byte LWF1 header, declared raw payload, CRC,
and low stop bit. Linux is notified only after a complete valid frame, so no
manual preset or byte count is entered.

The optical wire remains 25 ms per bit. The current receiver uses a measured
24,991-microsecond sampling interval to compensate the fixed oscillator offset
between the two workshop boards. This is a documented board-pair calibration,
not transition-based clock recovery; general clock recovery remains deferred.

Profile routing is automatic:

- `0x20` validates and stores 1-100 printable ASCII bytes as text. This path
  uses no AI model or accelerator.
- `0x01`, `0x02`, and `0x03` run the complete 64-, 128-, or 256-pixel image
  synthesis graph on Adreno Vulkan with neural CPU fallback forbidden.
- `0x10` reconstructs up to five seconds of audio using CPU codebooks and
  decoder layers 0-4 plus the strict 39-layer Adreno Vulkan suffix (layers
  5-15), then applies the disclosed boundary correction and exact sample trim.

The result page displays text, a PNG, or a playable WAV plus download, parsed
header, CRC/stop-bit, timing, device, and strict-assignment evidence. It has
persistent light/dark modes and reports STM32 optical-bit/CRC work, QRB2210 CPU
stages, Adreno 702 stages/audited layer counts, and peak decoder memory. Layer
counts are graph evidence, not FLOP or power estimates. Received raw payloads
and outputs are written atomically under `data/results`.

The same unchanged decode results are also queued for the standalone Galaxy
application. The receiver uses UNO Q's enabled `arduino-router-serial.service`
and the Router monitor methods `mon/read` and `mon/write`; the App Lab container
does not open `/dev/ttyGS0` and needs no custom Docker device grant. The phone
sends fixed `LWCT/1` Listen/Cancel/Status commands and receives CRC-protected
`LWRX/2` status, text, PNG, and WAV frames. Results remain in
`data/phone-outbox` until USB delivery succeeds. This downstream presentation
channel does not change `LWF1`, the optical bytes, the STM32 receiver sketch,
or the transmitter.

The tracked project contains no generated models or vendor libraries. Install
the base native receiver first, then deploy this App Lab application:

```powershell
.\scripts\install_uno_q.ps1 -DeviceSerial <RX_SERIAL> -DryRun
.\scripts\install_uno_q_optical_receiver.ps1 -DeviceSerial <RX_SERIAL> -DryRun
.\scripts\install_uno_q_optical_receiver.ps1 -DeviceSerial <RX_SERIAL> -StopRunningApp
```

After installation, either use the App Lab page or connect the Galaxy and tap
**Listen for transfer** in LightWeave Mobile. The final receiver/display runtime
is UNO Q plus phone and is local/offline; a laptop is needed only for setup and
development. The installer verifies that Arduino Router and its boot-managed
serial bridge are active before accepting the installation.

Physical acceptance on the project Galaxy S25 Ultra passed direct Status,
Listen, Cancel, and decoded-result display. A 9-byte `S25 PROOF` text payload
crossed the laser as a 21-byte `LWF1` frame in 4.25 seconds and reached the
phone with matching CRC `f8f8`, payload hash, and valid stop-bit evidence.
