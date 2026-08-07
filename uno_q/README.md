# LightWeave UNO Q media receiver

This target reconstructs existing header-free LightWeave image and EnCodec
audio payloads on the Arduino UNO Q. It is receiver-only: encoding, optical
audio reception, waveform redesign, and mobile delivery remain deferred.

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

The payload contains only the CompressAI entropy string. The preset is local
control-plane information and must match on sender and receiver.

Raw audio uses `A1-E15-S<n>`, where `n` is the exact output sample count at
24 kHz mono. Each started second is exactly 188 raw bytes. The initial board
limit is five seconds: at most 940 bytes and 120,000 output samples. The
settings code is communicated out of band and is not part of `payload.bin`.

## Transmitter companion

The separately tracked [`transmitter_app`](transmitter_app) project connects
the Windows dashboard to the transmitting UNO Q over USB/ADB. It is installed
as `lightweave_transmitter`, cloned from but independent of the board's
`image_transmitter_bkp` app. Its atomic inbox accepts image or audio raw bytes,
loads the exact variable length into the STM32, and retains the existing pin-9,
25-ms, MSB-first laser waveform.

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

## Production optical image receiver

[`optical_receiver_app`](optical_receiver_app) joins the diagnostic's proven
variable-length optical sampling with the already installed native image
decoder. The tracked app is installed as `lightweave_optical_receiver`; the
diagnostic and original `image_receiver` projects are not modified.

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

In App Lab, select the same image preset used by the transmitter, enter the
exact payload byte count, and arm the receiver before sending. The page
automatically displays/downloads the reconstructed PNG and reports payload
SHA-256, stop-bit state, entropy time, Adreno time, device, model hash, compute
layers, and no-fallback evidence.

Automated two-board acceptance:

```powershell
.\.venv-x64\Scripts\python.exe scripts\verify_uno_q_optical_image.py `
  artifacts\generated\uno_q\tiny.payload.bin `
  --preset I64-Q1-B128 `
  --output artifacts\generated\uno_q\optical-reconstruction.png `
  --transmitter-serial 123900964 `
  --receiver-serial 371371094
```

The exercised 80-byte fixture arrived with an exact SHA-256 and valid stop bit,
then reconstructed to 64 by 64 through all 16 image compute layers on Turnip
Adreno 702 with strict CPU fallback disabled. Optical audio reception remains a
later extension of the same boundary.

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
