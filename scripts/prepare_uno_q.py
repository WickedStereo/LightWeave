"""Prepare and validate the ignored LightWeave UNO Q image receiver bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import ncnn
import numpy as np
import onnxruntime as ort
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from export_image_decoder import export_decoder  # noqa: E402

from lightweave.image import load_image_model  # noqa: E402

MODEL_SHA256 = "446d5c7f56d4d5108dc7fb2532cbe45bbf2e78f1778384b04526a8fcd641f5c5"
NCNN_VERSION = "20260526"
PRESETS = (
    ("I64-Q1-B128", "tiny", 4, 64, 128),
    ("I128-Q1-B768", "balanced", 8, 128, 768),
    ("I256-Q1-B2048", "quality", 16, 256, 2048),
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tensor_array(value: object, dtype: np.dtype[object]) -> np.ndarray:
    if not isinstance(value, torch.Tensor):
        raise RuntimeError("CompressAI entropy metadata is not a tensor.")
    return np.asarray(value.detach().cpu().numpy(), dtype=dtype)


def write_entropy_tables(path: Path, weights: Path | None) -> dict[str, object]:
    model, weight_path, weight_hash = load_image_model(weights)
    if weight_hash.hex() != MODEL_SHA256:
        raise RuntimeError(
            "UNO Q artifacts require the pinned CompressAI weight fingerprint."
        )
    bottleneck = model.entropy_bottleneck
    cdf = _tensor_array(bottleneck._quantized_cdf, np.dtype("<u4"))
    lengths = _tensor_array(bottleneck._cdf_length, np.dtype("<u4")).reshape(-1)
    offsets = _tensor_array(bottleneck._offset, np.dtype("<i4")).reshape(-1)
    medians = _tensor_array(bottleneck._get_medians(), np.dtype("<f4")).reshape(-1)
    channels = int(bottleneck.channels)
    if channels != 192 or cdf.shape[0] != channels:
        raise RuntimeError("Unexpected CompressAI entropy table shape.")
    if not (len(lengths) == len(offsets) == len(medians) == channels):
        raise RuntimeError("CompressAI entropy table vectors do not match channels.")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(struct.pack("<4sHHHH", b"LWET", 1, channels, 16, 0))
        stream.write(weight_hash)
        for channel in range(channels):
            length = int(lengths[channel])
            values = cdf[channel, :length]
            if length < 2 or int(values[0]) != 0 or int(values[-1]) != 1 << 16:
                raise RuntimeError(f"Invalid entropy CDF for channel {channel}.")
            stream.write(
                struct.pack(
                    "<iIf", int(offsets[channel]), length, float(medians[channel])
                )
            )
            stream.write(values.tobytes(order="C"))
    return {
        "path": str(path.resolve()),
        "sha256": file_sha256(path),
        "format": "LWET-v1-little-endian",
        "channels": channels,
        "precision": 16,
        "source_weights": str(weight_path),
        "source_weights_sha256": weight_hash.hex(),
    }


def convert_with_pnnx(
    pnnx: Path, onnx_path: Path, output_dir: Path, stem: str, latent_size: int
) -> tuple[Path, Path]:
    param_path = output_dir / f"{stem}.ncnn.param"
    bin_path = output_dir / f"{stem}.ncnn.bin"
    command = [
        str(pnnx),
        str(onnx_path),
        f"inputshape=[1,192,{latent_size},{latent_size}]",
        f"pnnxparam={output_dir / f'{stem}.pnnx.param'}",
        f"pnnxbin={output_dir / f'{stem}.pnnx.bin'}",
        f"pnnxpy={output_dir / f'{stem}_pnnx.py'}",
        f"pnnxonnx={output_dir / f'{stem}.pnnx.onnx'}",
        f"ncnnparam={param_path}",
        f"ncnnbin={bin_path}",
        f"ncnnpy={output_dir / f'{stem}_ncnn.py'}",
        "fp16=1",
        "optlevel=2",
        "device=cpu",
    ]
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    if not param_path.is_file() or not bin_path.is_file():
        raise RuntimeError(f"pnnx did not create ncnn artifacts for {stem}.")
    return param_path, bin_path


def ncnn_cpu_parity(
    onnx_path: Path, param_path: Path, bin_path: Path, latent_size: int
) -> dict[str, object]:
    generator = np.random.default_rng(20260805 + latent_size)
    latent = generator.normal(size=(1, 192, latent_size, latent_size)).astype(
        np.float32
    )
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    reference = session.run(None, {"latent": latent})[0]
    with ncnn.Net() as net:
        net.opt.use_vulkan_compute = False
        if net.load_param(str(param_path)) != 0 or net.load_model(str(bin_path)) != 0:
            raise RuntimeError("Python ncnn could not load the converted graph.")
        with net.create_extractor() as extractor:
            if extractor.input("in0", ncnn.Mat(latent.squeeze(0)).clone()) != 0:
                raise RuntimeError("Python ncnn rejected the parity input.")
            status, output = extractor.extract("out0")
            if status != 0:
                raise RuntimeError("Python ncnn failed the parity inference.")
            actual = np.asarray(output, dtype=np.float32)[None, ...]
    if actual.shape != reference.shape or not np.isfinite(actual).all():
        raise RuntimeError("ncnn parity output has an invalid shape or value.")
    difference = actual - reference
    mse = float(np.mean(np.square(difference, dtype=np.float64)))
    psnr = math.inf if mse == 0 else 10.0 * math.log10(1.0 / mse)
    result = {
        "psnr_db": psnr,
        "maximum_absolute_error": float(np.max(np.abs(difference))),
        "mean_absolute_error": float(np.mean(np.abs(difference))),
        "threshold_db": 35.0,
        "passed": psnr >= 35.0,
    }
    if not result["passed"]:
        raise RuntimeError(f"ncnn CPU parity failed: {result}.")
    return result


def resolve_pnnx(value: Path | None) -> Path:
    if value is not None:
        candidate = value.resolve()
    else:
        executable = shutil.which("pnnx")
        if executable is None:
            raise RuntimeError("pnnx 20260526 is required to prepare UNO Q models.")
        candidate = Path(executable).resolve()
    if not candidate.is_file():
        raise RuntimeError(f"pnnx executable does not exist: {candidate}.")
    return candidate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "generated" / "uno_q",
    )
    parser.add_argument("--weights", type=Path)
    parser.add_argument("--pnnx", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    pnnx = resolve_pnnx(args.pnnx)

    result: dict[str, object] = {
        "schema_version": 1,
        "target": "Arduino UNO Q / Linux ARM64 / Adreno Vulkan",
        "model_sha256": MODEL_SHA256,
        "tools": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "onnxruntime": ort.__version__,
            "pnnx": NCNN_VERSION,
            "pnnx_executable": str(pnnx),
            "ncnn_python": getattr(ncnn, "__version__", NCNN_VERSION),
        },
        "entropy_tables": write_entropy_tables(
            output_dir / "entropy_tables.bin", args.weights
        ),
        "presets": [],
    }
    presets = result["presets"]
    assert isinstance(presets, list)
    for code, stem, latent_size, output_size, maximum_bytes in PRESETS:
        onnx_path = output_dir / f"{stem}.decoder.fp32.onnx"
        onnx_result = export_decoder(onnx_path, args.weights, latent_size)
        param_path, bin_path = convert_with_pnnx(
            pnnx, onnx_path, output_dir, stem, latent_size
        )
        presets.append(
            {
                "preset_code": code,
                "maximum_payload_bytes": maximum_bytes,
                "input_shape": [1, 192, latent_size, latent_size],
                "output_shape": [1, 3, output_size, output_size],
                "onnx": onnx_result,
                "ncnn": {
                    "version": NCNN_VERSION,
                    "parameter_path": str(param_path.resolve()),
                    "parameter_sha256": file_sha256(param_path),
                    "weights_path": str(bin_path.resolve()),
                    "weights_sha256": file_sha256(bin_path),
                    "fp16_storage": True,
                    "cpu_conversion_parity": ncnn_cpu_parity(
                        onnx_path, param_path, bin_path, latent_size
                    ),
                },
            }
        )
    manifest_path = output_dir / "bundle.manifest.json"
    manifest_path.write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "ok", "manifest": str(manifest_path)}, indent=2))


if __name__ == "__main__":
    main()
