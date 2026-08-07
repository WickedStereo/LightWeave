# LightWeave

[![CI](https://github.com/WickedStereo/LightWeave/actions/workflows/ci.yml/badge.svg)](https://github.com/WickedStereo/LightWeave/actions/workflows/ci.yml)

LightWeave is an offline text, image, and audio network for RF-denied spaces.
The Windows application creates compact payloads, hands them to an Arduino UNO
Q transmitter over USB, and sends a self-describing, CRC-protected frame over
visible light. A second UNO Q automatically identifies the media: printable
ASCII is restored directly, images run through a strict Adreno 702 decoder,
and audio runs through an explicitly labeled QRB2210 CPU/Adreno hybrid.

Three data representations coexist:

- Raw optical mode sends only codec bytes. Image presets reconstruct at
  64 x 64 / 128 bytes, 128 x 128 / 768 bytes, or 256 x 256 / 2,048 bytes.
  `A1-E15-S<n>` audio uses exactly 188 bytes per started second. The preset
  code travels separately.
- `.lwv` remains the self-validating archival and debugging format with typed
  metadata, length, model fingerprint, and SHA-256 integrity.
- `LWF1` is the optical-only wrapper around unchanged raw bytes. It carries the
  profile, dynamic payload length, audio sample count, and CRC-16 so the UNO Q
  receiver needs no manual preset or length entry.

## Team

The final public names and email addresses are intentionally not guessed from
Git metadata. The repository owner must replace this note with the complete
team roster before submitting the GitHub link.

The image path is fully NPU-backed. CompressAI creates an entropy-coded image
payload, the receiver restores the latent tensor on CPU, and the complete
fixed-shape `g_s` synthesis graph runs on Qualcomm QNN HTP with CPU fallback
disabled.

The audio extension uses Meta EnCodec at 24 kHz mono and exactly 1.5 kbps of
packed codes. It is an explicitly labeled hybrid: EnCodec decoder layers 0-12
run on CPU, while fixed decoder layers 13-15 run entirely on QNN HTP. A short
CPU de-click correction removes independent one-second chunk-edge steps.

## Verified on the development device

- Snapdragon X Elite X1E80100, Windows 11 ARM64.
- ONNX Runtime 1.24.4 with QNN plugin 2.4.0.
- Image acceptance set: 3/3 pass, maximum complete payload 1,444 bytes,
  27.67 dB mean PSNR, and 0.973 mean MS-SSIM.
- Complete image decoder profile: `QNNExecutionProvider` only, zero CPU nodes.
- Image CPU/NPU parity: at least 56.99 dB across the acceptance set.
- Audio acceptance sample: 1,500 code bits/sec, exact 48,000 samples restored,
  zero conditioned boundary jump, and 48.80 dB NPU-tail parity.
- Audio tail profile: `QNNExecutionProvider` only, zero CPU nodes.
- Runtime smoke-tested with non-loopback networking blocked in both workers.
- Raw image set: 4/4 deterministic payloads fit every profile. Tiny measured
  76-124 bytes, balanced 216-664 bytes, and quality 716-2,044 bytes. All three
  fixed decoders ran strictly on QNN with zero CPU nodes; balanced NPU/CPU
  parity was at least 51.29 dB.
- Raw audio sample: exactly 376 bytes for two seconds, 48,000 samples restored,
  and a strict zero-CPU-node QNN tail profile.
- UNO Q: all three raw image decoders run as complete 16-layer graphs through
  ncnn Vulkan on the Adreno 702 with CPU fallback rejected; board
  accelerator/CPU parity is 36.34-44.38 dB.
- UNO Q audio: split 5 is the earliest valid CPU/Adreno EnCodec partition.
  Its 39-layer Vulkan suffix runs on Adreno 702 with fallback rejected; the
  one-second board output reached 52.11 dB against PyTorch.

Generated reports, model weights, ONNX/QDQ artifacts, and profiles are ignored
by Git. Reproduce the evidence locally with the scripts below.

## Setup

The tested Windows setup uses Python 3.11 in two architectures:

- x64 for PyTorch, CompressAI, EnCodec, entropy coding, model preparation,
  CLI, tests, and dashboard.
- native ARM64 for ONNX Runtime plus the QNN plugin.

Install both signed Python interpreters and Visual Studio C++ Build Tools, then
run:

```powershell
.\scripts\setup_windows.ps1
```

Detailed prerequisites, manual steps, environment variables, and verification
commands are in [docs/SETUP_WINDOWS.md](docs/SETUP_WINDOWS.md).

## Commands

```powershell
# Images
lightweave image encode input.png --output payload.lwv
lightweave inspect payload.lwv
lightweave image decode payload.lwv --output reconstructed.png --require-npu
lightweave image roundtrip input.png --work-dir out\image

# Audio
lightweave audio encode input.wav --output audio.lwv
lightweave inspect audio.lwv
lightweave audio decode audio.lwv --output reconstructed.wav
lightweave audio roundtrip input.wav --work-dir out\audio

# Header-free raw codec payloads
lightweave raw image encode input.png --preset I128-Q1-B768 --output payload.bin
lightweave raw image decode payload.bin --preset I128-Q1-B768 --output image.png --require-npu
lightweave raw audio encode input.wav --output payload.bin
lightweave raw audio decode payload.bin --preset A1-E15-S48000 --output audio.wav

# Offline local UI
lightweave dashboard
```

The dashboard binds only to `127.0.0.1` and loads no remote assets. `/transmit`
generates no-AI text, image, and audio payloads and downloads the exact raw
`payload.bin`; `/receive` reconstructs uploaded image/audio payloads using
their out-of-band settings codes, and `/loopback` preserves
the `.lwv` development workbench. The monochrome text-first UI defaults to the
balanced 128 x 128 profile, includes tiny and quality alternatives plus three
local test patterns, and shows transfer estimates, quality/latency metrics,
playable media, QNN device selection, and strict provider evidence.
Every Windows and production UNO Q page includes a persistent light/dark mode
control that also respects the browser's initial system preference.

Hardware evidence is shown with each operation. Windows records process CPU
time, wall time, peak process memory, exact media counters, QNN device
selection, and execution-provider event counts. The transmitter reports ADB,
RouterBridge, buffered-byte, CRC-byte, optical-bit, and GPIO-write counts. The
receiver reports STM32 frame work plus QRB2210 CPU and Adreno 702 stage timing
and audited graph-layer counts. These are measured events and graph layers,
not inferred FLOPs, power, or energy figures.

Downloaded raw `payload.bin` files intentionally have no integrity or
model-negotiation bytes. The production laser path adds the small `LWF1`
length/profile/CRC wrapper at transmission time; use `.lwv` when SHA-256 and
model-fingerprint protections are required.

### Send a generated payload to UNO Q

The repository includes the complete App Lab transmitter source in
[`uno_q/transmitter_app`](uno_q/transmitter_app). It is deployed as a new app
named `lightweave_transmitter` and displayed as **LightWeave Transmitter**. The
owner's `image_transmitter_bkp` and `laser_transmitter_ui` projects are hashed
before and after installation and are never edited or started.

Connect one transmitting UNO Q by USB, then run:

```powershell
# Inspect the board and backup without changing anything.
.\scripts\install_uno_q_transmitter.ps1 -DryRun

# Clone the backup, install the tracked source, compile, and start the new app.
.\scripts\install_uno_q_transmitter.ps1

# If App Lab reports that another app is running, stop it reversibly and start
# the transmitter. No app is deleted.
.\scripts\install_uno_q_transmitter.ps1 -StopRunningApp

# Open the Windows transmitter UI.
lightweave dashboard
```

After generating text, image, or audio `payload.bin`, use **Send to Arduino**. The
dashboard pushes the exact bytes through an atomic ADB inbox; no Wi-Fi or
remote service is involved. If ADB is installed elsewhere, set
`LIGHTWEAVE_ADB_PATH`. With two UNO Q boards attached, LightWeave selects the
single board running the tracked transmitter. `LIGHTWEAVE_UNO_Q_SERIAL` remains
available as an explicit override.

The hardware adapter retains pin 9, 25 ms per bit, MSB-first ordering, one high
start bit, and one low stop bit. Its default `LWF1` wire frame adds a ten-byte
version/profile/length/media header and two-byte CRC around the unchanged raw
payload. The UI distinguishes payload bytes from total optical bytes and shows
the 40-bit/s estimate. Acceptance proves buffer count and launch; receiver
evidence proves physical completion separately.

### Verify optical bytes on a second UNO Q

The repository also tracks a minimal diagnostic receiver in
[`uno_q/byte_receiver_app`](uno_q/byte_receiver_app). It does not reconstruct
media. It receives an explicitly declared number of raw bits using the existing
A0 photodiode threshold and 25-ms timing, saves `received_payload.bin`, and
reports its SHA-256 and stop-bit result.

With both boards connected, pin their ADB serials so the dashboard never sends
to the receiver by mistake:

```powershell
$env:LIGHTWEAVE_UNO_Q_SERIAL = "123900964"
$env:LIGHTWEAVE_UNO_Q_RECEIVER_SERIAL = "371371094"

.\scripts\install_uno_q_byte_receiver.ps1 -DeviceSerial 371371094 -DryRun
.\scripts\install_uno_q_byte_receiver.ps1 -DeviceSerial 371371094 -StopRunningApp

.\.venv-x64\Scripts\python.exe scripts\verify_uno_q_optical_link.py `
  --transmitter-serial 123900964 `
  --receiver-serial 371371094 `
  --payload-hex 00ffaa55
```

Success requires `exact_match: true`, matching sent/received SHA-256 values,
and `stop_bit_valid: true`. The expected byte count travels only through the
local ADB control plane. This test explicitly selects legacy `raw-v0`; normal
dashboard sends use `LWF1`. The original receiver projects are not edited.

### Receive optical text, images, and audio

The production [`uno_q/optical_receiver_app`](uno_q/optical_receiver_app)
combines the A0 receiver with the installed native LightWeave decoders. It
parses `LWF1` and automatically identifies media and settings. Text is exact
printable ASCII and uses no AI. The same app reconstructs all three image
profiles or up to five seconds of EnCodec audio. Image graphs run completely
on Adreno 702; audio is accurately labeled CPU/Adreno hybrid.

Install the accelerated base once, then deploy the lightweight optical app:

```powershell
$env:LIGHTWEAVE_UNO_Q_RECEIVER_SERIAL = "371371094"
.\scripts\install_uno_q_optical_receiver.ps1 -DeviceSerial 371371094 -DryRun
.\scripts\install_uno_q_optical_receiver.ps1 -DeviceSerial 371371094 -StopRunningApp
```

Open **LightWeave Receiver** in App Lab and press **Listen for
transfer**, then press **Send to Arduino** in the Windows dashboard. No receiver
preset or byte count is entered. For automated physical acceptance with a
prepared image payload:

```powershell
.\.venv-x64\Scripts\python.exe scripts\verify_uno_q_optical_image.py `
  artifacts\generated\uno_q\tiny.payload.bin `
  --preset I64-Q1-B128 `
  --output artifacts\generated\uno_q\optical-reconstruction.png `
  --transmitter-serial 123900964 `
  --receiver-serial 371371094
```

For a short no-AI text transfer:

```powershell
.\.venv-x64\Scripts\python.exe scripts\verify_uno_q_optical_text.py `
  --text "Hello LightWeave" `
  --output artifacts\generated\uno_q\received.txt `
  --transmitter-serial 123900964 `
  --receiver-serial 371371094
```

The historical 100-ms `laser_transmitter_ui`/`laser_receiver_ui` waveform is
documented in [`uno_q/LEGACY_TEXT_PROTOCOL.md`](uno_q/LEGACY_TEXT_PROTOCOL.md).
It remains a compatibility reference; production text uses the shared 25-ms
LWF1 link with profile `T1-ASCII-B100`, dynamic length, and CRC.

For a short one-second audio fixture, use the companion command:

```powershell
.\.venv-x64\Scripts\python.exe scripts\verify_uno_q_optical_audio.py `
  artifacts\generated\uno_q\audio-1s.payload.bin `
  --preset A1-E15-S24000 `
  --output artifacts\generated\uno_q\optical-reconstruction.wav `
  --transmitter-serial 123900964 `
  --receiver-serial 371371094
```

Success requires a valid `LWF1` header/CRC/stop bit, exact output dimensions or
sample count, an Adreno device, and strict no-fallback evidence for the image
graph or audio suffix. The diagnostic, original `image_receiver`, and installed
base decoder remain separate and unchanged.

### Optional three-lane optical sketches

For the three-laser workshop setup, the repository also tracks separate
**LightWeave Parallel Transmitter** and **LightWeave Parallel Receiver** App Lab
clones. The standard apps remain installed and their source hashes are checked
before and after every parallel-app installation. The clones reuse the existing
Python services, codecs, receiver WebUI, phone transport, and accelerated media
reconstruction unchanged; only their STM32 sketches implement the parallel
wire behavior.

- Transmitter lanes: D5, D7, and D9.
- Receiver lanes: A0, A2, and A5, each with threshold 800.
- Complete `LWF1` frame bytes are striped round-robin across the three lanes.
- All lanes retain the common high start bit, 25-ms MSB-first data timing, and
  common low stop bit.
- The receiver restores the original frame before applying the existing
  profile, length, CRC-16, text/audio, and stop-bit checks.

Install the standard pair first, align each laser to only its matching sensor,
then install the separate clones:

```powershell
.\scripts\install_uno_q_parallel_transmitter.ps1 `
  -DeviceSerial 123900964 -DryRun
.\scripts\install_uno_q_parallel_receiver.ps1 `
  -DeviceSerial 371371094 -DryRun

.\scripts\install_uno_q_parallel_transmitter.ps1 `
  -DeviceSerial 123900964 -StopRunningApp
.\scripts\install_uno_q_parallel_receiver.ps1 `
  -DeviceSerial 371371094 -StopRunningApp

$env:LIGHTWEAVE_UNO_Q_TRANSMITTER_APP = "parallel"
$env:LIGHTWEAVE_UNO_Q_SERIAL = "123900964"
.\.venv-x64\Scripts\lightweave.exe dashboard

.\.venv-x64\Scripts\python.exe scripts\verify_uno_q_parallel_text.py `
  --text "3-LANE" `
  --transmitter-serial 123900964 `
  --receiver-serial 371371094
```

App Lab runs only one application per board, so starting a parallel clone stops
the active standard app but does not delete or overwrite it. The physical gate
received exact `3-LANE` bytes in six parallel byte slots: 1.25 seconds versus
3.65 seconds for the same 18-byte frame on one lane. D5/A0 also passed a
60-second alignment hold with all 60 readings above threshold. Isolate the
three optical paths before media tests; a lane seeing another laser can corrupt
symbols even though CRC prevents reconstruction of a bad frame.

Open `http://127.0.0.1:8765/transmit` after starting the executable. The
`LIGHTWEAVE_UNO_Q_TRANSMITTER_APP` selector is restricted to `standard` or
`parallel`; omitting it preserves the original standard-app behavior. Because
the cloned Python service is intentionally unchanged, its dashboard busy timer
and displayed optical estimate remain the conservative single-lane values even
though the three lasers physically finish sooner.

For the standalone display gate, the parallel receiver was selected as the
board's reversible boot default and connected directly to the S25. The existing
LightWeave Mobile Listen control armed it, and exact `PHONE 3-LANE` appeared in
the unchanged Android app after a 12-byte payload/24-byte frame crossed eight
parallel slots in 1.65 seconds.

## Standalone Galaxy receiver/display

The fresh [`android/`](android/) Android Studio project replaces the earlier
prototype and makes the final receiver-side display **Galaxy S25 Ultra + UNO Q
only**. A laptop is needed for one-time installation and development, but is
not present at runtime. The phone controls the production receiver and the UNO
Q retains all optical validation and reconstruction work. The app:

- matches the observed UNO Q USB identity `2341:0078`;
- reads CDC/ACM through pinned `usb-serial-for-android` 3.10.0;
- sends CRC-protected **Listen**, **Cancel**, and **Status** controls;
- parses metadata-rich, CRC-protected `LWRX/2` result frames;
- displays/saves text and PNG, plays/saves WAV audio, and shows the same
  optical, CPU, Adreno, STM32, timing, and model evidence as the receiver page;
- provides a plain persistent light/dark UI; and
- requests neither Internet nor broad storage permission.

The receiver service uses UNO Q's boot-managed Arduino Router monitor rather
than opening `/dev/ttyGS0` inside its App Lab container. This removes the custom
Compose device grant that App Lab dropped on default-app boot. The durable phone
outbox has passed duplex control/status plus a real reconstructed-PNG delivery
test through the UNO Q USB gadget, and the supported Router path has returned a
valid CRC-checked status frame over the physical CDC interface. The same debug
build is installed and visually verified on a real Galaxy S25 Ultra
(`SM-S938U1`, Android 15), including its light/dark UI. Direct Galaxy-to-UNO-Q
enumeration, Status, Listen, Cancel, and result display now pass. A physical
9-byte `S25 PROOF` payload crossed the existing laser link as a 21-byte `LWF1`
frame and rendered on the phone with matching CRC, stop-bit, payload hash, and
hardware evidence. Direct image/audio display, reconnect, and longer sustained
phone power remain physical gates. See
[android/README.md](android/README.md) for setup, standalone usage, powered-hub
guidance, and both USB protocols.

## UNO Q accelerated media receiver

The [`uno_q/`](uno_q/) target receives the same header-free `payload.bin` and
reconstructs 64, 128, or 256-pixel images plus up to five seconds of 24 kHz
mono audio on the board. Its native ARM64 CLI runs directly on the existing
Debian OS—Docker is not a runtime dependency. Image synthesis runs completely
on Turnip Adreno 702 through ncnn Vulkan. Audio is explicitly hybrid:
unpacking, codebooks, and recurrent decoder layers 0-4 use CPU, while decoder
layers 5-15 form a strict 39-compute-layer Vulkan suffix on Adreno.

The repository provides source, a pinned manifest, preparation/packaging
scripts, a hash-checking installer with `-DryRun`, an offline-bundle option,
native commands, and a monochrome App Lab receive page with PNG/WAV download
and audio playback. Generated models,
vendor runtime files, and bundles remain ignored. See
[uno_q/README.md](uno_q/README.md) for build, install, evidence, commands, and
API details.

## Reproduce acceptance evidence

```powershell
.\.venv-x64\Scripts\python.exe -m pytest -q
.\.venv-x64\Scripts\python.exe -m ruff check .
.\.venv-x64\Scripts\python.exe scripts\evaluate_image_set.py --backend qnn
.\.venv-x64\Scripts\python.exe scripts\evaluate_audio.py
.\.venv-x64\Scripts\python.exe scripts\evaluate_raw.py --image-backend qnn --audio data\generated\demo-audio\chirp-and-tones.wav --audio-backend hybrid-qnn
.\.venv-x64\Scripts\python.exe scripts\offline_smoke.py
```

## Scope and records

Analog redesign, transition-based clock recovery, faster modulation, direct
Galaxy-to-UNO-Q physical validation, and Cloud AI remain outside the verified
milestone. The tracked UNO Q pair now automatically carries and
reconstructs image and one-second audio fixtures through `LWF1`; the supported
five-second audio decoder was not subjected to the intentionally long optical
stress transfer.

- [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) is the living source of truth.
- [docs/QUALCOMM_DEVELOPER_EXPERIENCE.md](docs/QUALCOMM_DEVELOPER_EXPERIENCE.md)
  records Qualcomm tools, evidence, friction, and improvement suggestions.
- [data/demo_manifest.json](data/demo_manifest.json) defines the public image
  acceptance set and oversize stress case.
- [models/manifest.json](models/manifest.json) pins model sources, hashes,
  profiles, shapes, and expected generated artifacts.
- [docs/SUBMISSION_CHECKLIST.md](docs/SUBMISSION_CHECKLIST.md) audits the
  repository against the hackathon delivery requirements and identifies the
  remaining owner-only actions.

Licensed under the [MIT License](LICENSE).
