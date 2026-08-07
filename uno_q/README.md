# LightWeave UNO Q media receiver

This target reconstructs existing header-free LightWeave image and EnCodec
audio payloads on the Arduino UNO Q. Its production App Lab path now receives
both media types through self-describing `LWF1` optical frames. It remains
receiver-only: encoding, waveform redesign, and mobile delivery are deferred.

For images, entropy decoding and PNG packaging run on the ARM64 CPU. The
complete CompressAI `g_s` graph runs through ncnn Vulkan on Turnip Adreno 702;
the runner rejects unsupported layers, non-Adreno devices, and neural CPU
fallback. Audio is an explicit hybrid: 10-bit unpacking, codebook summation,
and EnCodec decoder layers 0-4 run on CPU, while complete decoder layers 5-15
run on Adreno. Audio is never described as full-GPU or NPU inference.

Supported presets are unchanged:

| Preset | Maximum raw bytes | Exact output |
| --- | ---: | ---: |
| `I64-Q1-B128` | 128 | 64 x 64 |
| `I128-Q1-B768` | 768 | 128 x 128 |
| `I256-Q1-B2048` | 2,048 | 256 x 256 |

The saved payload contains only the CompressAI entropy string. Standalone decode
still takes an out-of-band preset; the production optical frame supplies its
profile automatically.

Raw audio uses `A1-E15-S<n>`, where `n` is the exact output sample count at
24 kHz mono. Each started second is exactly 188 raw bytes. The initial board
limit is five seconds: at most 940 bytes and 120,000 output samples. The
settings code is communicated out of band for standalone files and is not part
of `payload.bin`; `LWF1` carries the equivalent profile/sample metadata on the
laser wire.

Raw text uses `T1-ASCII-B100`: 1-100 printable ASCII bytes, sent unchanged and
decoded without an AI model. Production LWF1 profile ID `0x20` supplies its
type, dynamic length, and CRC on the laser wire. The original stopped
`laser_transmitter_ui` and `laser_receiver_ui` protocol is preserved as an
observed compatibility reference in
[`LEGACY_TEXT_PROTOCOL.md`](LEGACY_TEXT_PROTOCOL.md).

## Transmitter companion

The separately tracked [`transmitter_app`](transmitter_app) project connects
the Windows dashboard to the transmitting UNO Q over USB/ADB. It is installed
as `lightweave_transmitter`, cloned from but independent of the board's
`image_transmitter_bkp` app. Its App Lab display name is **LightWeave
Transmitter**. Its atomic inbox accepts text, image, or audio raw bytes,
loads the exact variable length into the STM32, and retains the existing pin-9,
25-ms, MSB-first laser waveform. The STM32 adds `LWF1` only while transmitting;
the saved raw payload is never rewritten or padded.

```powershell
.\scripts\install_uno_q_transmitter.ps1 -DryRun
.\scripts\install_uno_q_transmitter.ps1 -StopRunningApp
lightweave dashboard
```

The installer stages only repository-tracked source, refuses to overwrite an
unrelated target, verifies the backup hashes before and after deployment, and
supports `-NoStart`. The dashboard never starts or flashes an app when Send is
clicked. See [`transmitter_app/README.md`](transmitter_app/README.md) for the
wire behavior and milestone boundary.

## Optical byte receiver diagnostic

[`byte_receiver_app`](byte_receiver_app) is a separate App Lab project for
validating transport before reconstruction. It is armed with an expected byte
count, samples the existing A0/threshold-800 receiver at 25 ms per bit,
retrieves the STM32 result in 32-byte chunks, and saves the exact binary payload
plus SHA-256 evidence.

```powershell
.\scripts\install_uno_q_byte_receiver.ps1 -DeviceSerial 371371094 -DryRun
.\scripts\install_uno_q_byte_receiver.ps1 -DeviceSerial 371371094 -StopRunningApp
.\.venv-x64\Scripts\python.exe scripts\verify_uno_q_optical_link.py `
  --transmitter-serial 123900964 `
  --receiver-serial 371371094 `
  --payload-hex 00ffaa55
```

This diagnostic does not invoke CompressAI, EnCodec, ncnn, or the accelerated
receiver. Length remains trusted out-of-band data. It is kept as a focused
transport troubleshooting tool.

## Production text/image/audio receiver

[`optical_receiver_app`](optical_receiver_app) joins optical sampling with
no-AI text handling and the installed native image/audio decoders. The tracked
app is installed as `lightweave_receiver` and displayed as **LightWeave
Receiver**. The former `lightweave_optical_receiver`, diagnostic, and original
`image_receiver`/`laser_receiver_ui` projects are not modified.

Install the base decoder once with `install_uno_q.ps1`, then deploy only the
small optical integration layer:

```powershell
$env:LIGHTWEAVE_UNO_Q_RECEIVER_SERIAL = "371371094"
.\scripts\install_uno_q_optical_receiver.ps1 -DeviceSerial 371371094 -DryRun
.\scripts\install_uno_q_optical_receiver.ps1 -DeviceSerial 371371094 -StopRunningApp
```

The installer verifies the board's decoder source against this repository,
clones its hash-verified models/runtime, preserves the original receiver source
hashes, installs tracked App Lab/STM32 code, and supports `-NoStart`. It never
rebuilds ncnn or regenerates models.

In App Lab, press **Listen for transfer**, then send from the Windows dashboard.
The receiver reads the `LWF1` profile, length, and audio sample count, validates
CRC/stop bit, and routes the raw bytes automatically. It displays/downloads
text, PNG, or playable WAV output and reports frame plus applicable CPU,
Adreno, model, and strict-assignment evidence. **Cancel** returns an armed
receiver to idle without auto-rearming.

Automated two-board acceptance:

```powershell
.\.venv-x64\Scripts\python.exe scripts\verify_uno_q_optical_image.py `
  artifacts\generated\uno_q\tiny.payload.bin `
  --preset I64-Q1-B128 `
  --output artifacts\generated\uno_q\optical-reconstruction.png `
  --transmitter-serial 123900964 `
  --receiver-serial 371371094

.\.venv-x64\Scripts\python.exe scripts\verify_uno_q_optical_audio.py `
  artifacts\generated\uno_q\audio-1s.payload.bin `
  --preset A1-E15-S24000 `
  --output artifacts\generated\uno_q\optical-reconstruction.wav `
  --transmitter-serial 123900964 `
  --receiver-serial 371371094
```

Physical acceptance passed 80-, 216-, and 716-byte image fixtures through the
64-, 128-, and 256-pixel strict Adreno graphs. A 188-byte one-second audio frame
produced exactly 24,000 finite PCM samples using the truthful CPU plus strict
39-layer Adreno suffix. Further long optical transfers, including the
190.45-second five-second audio case, were intentionally skipped at the owner's
request; native five-second decode validation remains recorded separately.

The transmitter remains at 25,000 microseconds per bit. The receiver currently
samples at 24,991 microseconds after CRC evidence isolated cumulative phase
drift on the workshop board pair. This is calibration, not general clock
recovery; future transport work should replace it with transition-based timing.

## Optional three-lane sketch pair

[`parallel_transmitter_app`](parallel_transmitter_app) and
[`parallel_receiver_app`](parallel_receiver_app) are separate clones of the
standard applications. Their Python, WebUI, phone, codec, and reconstruction
components are reused unchanged; only the STM32 sketches differ. The complete
existing `LWF1` frame is striped over D5/D7/D9 and reassembled from A0/A2/A5.

```powershell
.\scripts\install_uno_q_parallel_transmitter.ps1 -DeviceSerial 123900964 -DryRun
.\scripts\install_uno_q_parallel_receiver.ps1 -DeviceSerial 371371094 -DryRun
.\scripts\install_uno_q_parallel_transmitter.ps1 -DeviceSerial 123900964 -StopRunningApp
.\scripts\install_uno_q_parallel_receiver.ps1 -DeviceSerial 371371094 -StopRunningApp

.\.venv-x64\Scripts\python.exe scripts\verify_uno_q_parallel_text.py `
  --text "3-LANE" `
  --transmitter-serial 123900964 `
  --receiver-serial 371371094
```

Before sending, verify that D5 alone crosses only A0 threshold 800, D7 alone
crosses only A2, and D9 alone crosses only A5. The exercised board pair passed
high masks 1, 2, 4, and 7, a 60-second D5/A0 hold, and exact six-byte LWF1 text
reassembly with matching CRC and valid stop bit. App Lab permits one active app
per board; the installers preserve the standard app sources and stop another
app only when `-StopRunningApp` is explicitly supplied.

## Runtime architecture

`lightweave-uno` is a native host CLI and does not need Docker at runtime. Its
statically linked native runner talks to the board's existing Vulkan stack.
The optional App Lab UI uses Arduino's normal application container, while the
installer copies the target board's own Vulkan loader, Turnip driver, and ICD
descriptor into that app directory. Those board-owned files are not committed
or redistributed.

The checked-in source never contains model weights, converted ncnn artifacts,
vendor binaries, or device data. `models/manifest.json` records their source
and expected locations; generated bundles live below ignored
`artifacts/generated/uno_q/`. `SBOM.spdx.json` and the native third-party
notice travel with every offline bundle.

## Prepare and package

From the repository's pinned Windows x64 Python environment, prepare image and
audio artifacts:

```powershell
.\.venv-x64\Scripts\python.exe scripts\prepare_uno_q.py
.\.venv-x64\Scripts\python.exe scripts\prepare_uno_q_audio.py --selected-split 5
```

Build `uno_q/native` for Debian ARM64 with ncnn Vulkan enabled and place the
result at `artifacts/generated/uno_q/lightweave-uno-runner`. The reproducible
builder definition is `uno_q/docker/Dockerfile.runner`; it is a build-time
convenience only. A first ncnn build took about 27 minutes with two compile
jobs on the exercised UNO Q, while cached native-runner rebuilds took about 20
seconds. Build duration is hardware, storage, temperature, and cache dependent.

Create the hash-verified offline bundle:

```powershell
.\.venv-x64\Scripts\python.exe scripts\package_uno_q.py
```

## Install

Connect one UNO Q over ADB and run the non-mutating preflight first:

```powershell
.\scripts\install_uno_q.ps1 -DryRun
.\scripts\install_uno_q.ps1
```

The installer checks the bundle hashes, ARM64 architecture, free disk, and App
Lab CLI. It installs only `/home/arduino/ArduinoApps/lightweave-uno`, creates a
user-local command symlink, validates strict Adreno inference, and restarts
that one app. It does not install OS packages, delete other applications, or
modify the base image.

An already prepared bundle can be carried to an offline workstation and passed
with `-OfflineBundle`. Use `-DeviceSerial` when more than one ADB target exists.

## Commands and API

```text
lightweave-uno doctor --json
lightweave-uno image decode payload.bin --preset I128-Q1-B768 --output image.png --require-accelerator
lightweave-uno benchmark --preset all --json
lightweave-uno audio decode payload.bin --preset A1-E15-S48000 --output audio.wav --require-accelerator
lightweave-uno audio benchmark --seconds 1 --runs 5 --json
lightweave-uno serve
```

The board-local service provides:

```text
GET  /api/status
GET  /api/presets
POST /api/receive/image?preset=I128-Q1-B768
POST /api/receive/audio?preset=A1-E15-S48000
```

The POST body is `application/octet-stream`; its raw bytes remain identical to
the future optical payload. Responses contain a base64 PNG or WAV plus
execution evidence for the local WebUI only. The service binds to localhost by
default and uses no remote assets.

## Validated board evidence

- Arduino UNO Q, Debian 13.1 ARM64, 3.6 GiB RAM.
- Mesa 25.2.6 Turnip Vulkan on Adreno 702.
- Native rANS latent equality with CompressAI for all three presets.
- Full 16-compute-layer Vulkan graph for every preset, strict no-fallback.
- GPU/CPU reconstruction parity: 36.34 dB (64), 41.77 dB (128), and 44.38 dB
  (256).
- Warm reconstruction measurements: approximately 0.17 s, 0.52 s, and 1.98 s
  respectively for the exercised fixtures.
- Five-run median/p95 accelerator measurements: 0.173/0.176 s, 0.521/0.562
  s, and 1.978/2.160 s. Observed peak child RSS was at most about 60.6 MiB;
  the installed app bundle occupied about 35.6 MiB.
- EnCodec split candidate 2 was rejected because its suffix produced
  non-finite Vulkan output. Split 5 was the earliest passing candidate.
- The split-5 one-second suffix executed 39 Vulkan compute layers on Adreno;
  complete board output reached 52.11 dB against the PyTorch reference.
- Five-run one-second median/p95 was 1.306/1.317 s for the Adreno suffix and
  2.716/2.745 s end to end. Five-second median/p95 was 6.248/6.249 s on Adreno
  and 8.483/8.487 s end to end; peak observed child RSS was about 109.1 MiB.

The stable runner keeps FP16 packing/storage but uses FP32 arithmetic. An
earlier FP16-arithmetic stress sequence triggered a recoverable MSM GPU hang
on repeated 256-pixel runs. Accelerator calls are now serialized across the
native CLI and App Lab container through a shared lock with a one-second
cooldown; the final five-run test across every profile passed. Do not run an
uncoordinated second Vulkan client against the LightWeave models.

QNN/FastRPC libraries and device nodes were not present on the exercised base
image, so this milestone makes an Adreno Vulkan claim, not a Hexagon claim.
