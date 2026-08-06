# LightWeave UNO Q image receiver

This target reconstructs existing header-free LightWeave image payloads on the
Arduino UNO Q. Entropy decoding and PNG packaging run on the ARM64 CPU. The
complete CompressAI `g_s` synthesis graph runs through ncnn Vulkan on the
board's Turnip Adreno 702 device; the runner rejects unsupported layers,
non-Adreno devices, and any neural CPU fallback.

Supported presets are unchanged:

| Preset | Maximum raw bytes | Exact output |
| --- | ---: | ---: |
| `I64-Q1-B128` | 128 | 64 x 64 |
| `I128-Q1-B768` | 768 | 128 x 128 |
| `I256-Q1-B2048` | 2,048 | 256 x 256 |

The payload contains only the CompressAI entropy string. The preset is local
control-plane information and must match on sender and receiver.

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

From the repository's pinned Windows x64 Python environment:

```powershell
.\.venv-x64\Scripts\python.exe scripts\prepare_uno_q.py
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
lightweave-uno serve
```

The board-local service provides:

```text
GET  /api/status
GET  /api/presets
POST /api/receive/image?preset=I128-Q1-B768
```

The POST body is `application/octet-stream`; its raw bytes remain identical to
the future optical payload. The response contains a base64 PNG and execution
evidence for the local WebUI only.

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

The stable runner keeps FP16 packing/storage but uses FP32 arithmetic. An
earlier FP16-arithmetic stress sequence triggered a recoverable MSM GPU hang
on repeated 256-pixel runs. Accelerator calls are now serialized across the
native CLI and App Lab container through a shared lock with a one-second
cooldown; the final five-run test across every profile passed. Do not run an
uncoordinated second Vulkan client against the LightWeave models.

QNN/FastRPC libraries and device nodes were not present on the exercised base
image, so this milestone makes an Adreno Vulkan claim, not a Hexagon claim.
