# LightWeave

[![CI](https://github.com/WickedStereo/LightWeave/actions/workflows/ci.yml/badge.svg)](https://github.com/WickedStereo/LightWeave/actions/workflows/ci.yml)

LightWeave turns images and PCM WAV audio into compact bytes for an extremely
low-bandwidth, air-gapped link. The current software treats the future
Arduino/optical layer as a reliable ordered, message-bounded byte pipe: encode
on one host, transfer the bytes unchanged, and reconstruct on a Snapdragon
receiver.

Two wire formats coexist:

- Raw optical mode sends only codec bytes. `I64-Q1` images are at most 128
  bytes and reconstruct to exactly 64×64. `A1-E15-S<n>` audio uses exactly 188
  bytes per started second. The preset code travels separately.
- `.lwv` remains the self-validating archival and debugging format with typed
  metadata, length, model fingerprint, and SHA-256 integrity.

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
- Raw image set: 4/4 payloads at or below 128 bytes, deterministic output,
  strict full-decoder QNN profiles with zero CPU nodes, and at least 59.92 dB
  NPU/CPU parity. Reconstruction quality is informational at this wire budget.
- Raw audio sample: exactly 376 bytes for two seconds, 48,000 samples restored,
  and a strict zero-CPU-node QNN tail profile.

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

# Header-free raw optical payloads
lightweave raw image encode input.png --output payload.bin
lightweave raw image decode payload.bin --preset I64-Q1 --output image.png --require-npu
lightweave raw audio encode input.wav --output payload.bin
lightweave raw audio decode payload.bin --preset A1-E15-S48000 --output audio.wav

# Offline local UI
lightweave dashboard
```

The dashboard binds only to `127.0.0.1` and loads no remote assets. `/transmit`
generates and downloads the exact raw `payload.bin`, `/receive` reconstructs an
uploaded payload using its out-of-band settings code, and `/loopback` preserves
the `.lwv` development workbench. The pages show transfer estimates,
quality/latency metrics, playable media, QNN device selection, and strict
provider evidence.

Raw mode intentionally has no integrity or model-negotiation bytes. Corruption,
wrong message boundaries, or mismatched pinned artifacts may fail decoding or
produce incorrect media; use `.lwv` when those protections are required.

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

Laser/LED hardware, photodiodes, Arduino firmware, serial framing, Galaxy S25,
and Cloud AI remain outside this software milestone. A later serial adapter can
carry `.lwv` unchanged.

- [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) is the living source of truth.
- [docs/QUALCOMM_DEVELOPER_EXPERIENCE.md](docs/QUALCOMM_DEVELOPER_EXPERIENCE.md)
  records Qualcomm tools, evidence, friction, and improvement suggestions.
- [data/demo_manifest.json](data/demo_manifest.json) defines the public image
  acceptance set and oversize stress case.
- [models/manifest.json](models/manifest.json) pins model sources, hashes,
  profiles, shapes, and expected generated artifacts.

Licensed under the [MIT License](LICENSE).
