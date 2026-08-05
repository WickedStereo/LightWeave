# Windows on Snapdragon setup

This guide reproduces the tested LightWeave environment on Windows 11 ARM64.
Setup and model preparation may use the internet. Encode, inspect, decode,
dashboard, and loopback operation are offline after artifacts are prepared.

## Prerequisites

1. Snapdragon X-series Windows PC with a working Qualcomm NPU driver.
2. Signed CPython 3.11 x64 and ARM64 installations.
3. Visual Studio 2022 C++ Build Tools. CompressAI 1.2.8 builds a small native
   extension because no suitable Windows wheel is published.
4. PowerShell 5.1 or newer.
5. Enough free space for two environments and downloaded weights. Generated
   files stay outside Git.

The setup script defaults to these interpreter locations:

```text
%LOCALAPPDATA%\Programs\Python\Python311-x64\python.exe
%LOCALAPPDATA%\Programs\Python\Python311-arm64\python.exe
```

Override `-X64Python` or `-Arm64Python` if needed.

## Automated setup

From the repository root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup_windows.ps1
```

The script:

1. Creates `.venv-x64` and `.venv-arm64`.
2. Installs the pinned requirements in the correct architecture.
3. Installs Meta EnCodec without its optional `torchaudio` dependency. The
   tested PyTorch 2.13 build has no matching torchaudio release, so LightWeave
   uses its own PCM WAV reader/writer and does not invoke EnCodec's file CLI.
4. Downloads both model checkpoints, verifies SHA-256, and stores them under
   ignored `models/weights/`.
5. Generates deterministic non-confidential image/audio calibration inputs.
6. Exports CPU-parity ONNX graphs and generates QNN QDQ artifacts.

No model, calibration data, profile, token, or credential is committed.

## Tested package matrix

| Environment | Packages |
| --- | --- |
| x64 codec | Python 3.11.9, NumPy 1.26.4, PyTorch 2.13.0, torchvision 0.28.0, CompressAI 1.2.8, EnCodec 0.1.1, ONNX 1.19.0, ONNX Runtime 1.24.4 |
| ARM64 NPU | Python 3.11.9, NumPy 1.26.4, ONNX Runtime 1.24.4, `onnxruntime-qnn` 2.4.0 |

Do not install plain `onnxruntime` and `onnxruntime-qnn` into the same ARM64
environment. They can overwrite the same runtime DLLs. LightWeave deliberately
uses separate environments.

## Model preparation commands

Run these manually when iterating on a graph:

```powershell
.\.venv-x64\Scripts\python.exe scripts\prepare_models.py
.\.venv-x64\Scripts\python.exe scripts\generate_demo_images.py
.\.venv-x64\Scripts\python.exe scripts\generate_demo_audio.py

.\.venv-x64\Scripts\python.exe scripts\export_image_decoder.py
.\.venv-x64\Scripts\python.exe scripts\quantize_image_decoder.py

.\.venv-x64\Scripts\python.exe scripts\export_audio_tail.py
.\.venv-x64\Scripts\python.exe scripts\quantize_audio_tail.py
```

Image QDQ uses unsigned 16-bit activations and weights. The audio tail uses
unsigned 16-bit activations with unsigned 8-bit weights; 16-bit audio weights
overflowed bias quantization ranges and failed the fidelity gate.

## Runtime and verification

The editable install creates the `lightweave` command in `.venv-x64\Scripts`.
Activate it or call the executable directly:

```powershell
.\.venv-x64\Scripts\Activate.ps1
lightweave --help
lightweave dashboard
```

Run the focused validation suite:

```powershell
python -m pytest -q
python -m ruff check .
python scripts\evaluate_image_set.py --backend qnn
python scripts\evaluate_audio.py
python scripts\offline_smoke.py
```

`LIGHTWEAVE_ENFORCE_OFFLINE=1` installs a process guard that blocks DNS and
non-loopback socket connections in the x64 controller and both ARM64 workers.
Loopback remains available for the dashboard.

## Optional environment variables

| Variable | Purpose |
| --- | --- |
| `LIGHTWEAVE_MODEL_DIR` | Directory containing both pinned weight files |
| `LIGHTWEAVE_IMAGE_WEIGHTS` | Explicit CompressAI checkpoint path |
| `LIGHTWEAVE_AUDIO_WEIGHTS` | Explicit EnCodec checkpoint path |
| `LIGHTWEAVE_ARM64_PYTHON` | Native ARM64 worker interpreter |
| `LIGHTWEAVE_IMAGE_DECODER_ONNX` | Generated image QDQ graph |
| `LIGHTWEAVE_AUDIO_TAIL_ONNX` | Generated audio-tail QDQ graph |
| `LIGHTWEAVE_ENFORCE_OFFLINE` | Set to `1` to reject non-loopback networking |

Use environment variables or an ignored local `.env`; never commit tokens or
credentials.

## Common failures

- `CompressAI` build fails: install the MSVC C++ workload and recreate the x64
  environment.
- No QNN NPU device: confirm native ARM64 Python, matching plugin/runtime
  versions, and current Qualcomm NPU drivers.
- CPU fallback error: the selected graph was not fully accepted by HTP. Do not
  remove the strict fallback setting; inspect the generated profile instead.
- Model fingerprint mismatch: rerun preparation with the tracked manifest and
  transfer the generated artifacts together with the pinned weights.
