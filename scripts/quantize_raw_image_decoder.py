"""Quantize a fixed raw-image decoder for strict QNN HTP execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
import torch
from onnxruntime.quantization import CalibrationDataReader, QuantType, quantize
from onnxruntime.quantization.execution_providers.qnn import (
    get_qnn_qdq_config,
    qnn_preprocess_model,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightweave.image import load_image_model  # noqa: E402
from lightweave.metrics import array_psnr  # noqa: E402
from lightweave.paths import generated_artifact_dir  # noqa: E402
from lightweave.raw import (  # noqa: E402
    RAW_IMAGE_PRESET,
    RAW_IMAGE_PRESETS,
    RawImagePreset,
    parse_raw_image_preset,
    raw_image_candidate,
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class LatentReader(CalibrationDataReader):
    def __init__(self, values: list[np.ndarray]) -> None:
        self.values = values
        self._iterator: Any = None
        self.rewind()

    def get_next(self) -> dict[str, np.ndarray] | None:
        return next(self._iterator, None)

    def rewind(self) -> None:
        self._iterator = iter({"latent": value} for value in self.values)


def calibration_latents(
    image_paths: list[Path], preset: RawImagePreset
) -> list[np.ndarray]:
    from PIL import Image, ImageOps

    model, _, _ = load_image_model()
    values: list[np.ndarray] = []
    with torch.inference_mode():
        for image_path in image_paths:
            with Image.open(image_path) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
            for detail in preset.detail_levels:
                candidate = raw_image_candidate(image, detail, preset)
                array = np.asarray(candidate, dtype=np.float32) / 255.0
                tensor = (
                    torch.from_numpy(array)
                    .permute(2, 0, 1)
                    .unsqueeze(0)
                    .contiguous()
                )
                compressed = model.compress(tensor)
                latent = model.entropy_bottleneck.decompress(
                    compressed["strings"][0], compressed["shape"]
                )
                values.append(latent.cpu().numpy().astype(np.float32, copy=False))
    return values


def load_acceptance_images(manifest_path: Path, image_dir: Path) -> list[Path]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = [image_dir / name for name in manifest["acceptance_images"]]
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Generated calibration images are missing. Run "
            "`python scripts/generate_demo_images.py` first: "
            + ", ".join(str(path) for path in missing)
        )
    return paths


def quantize_decoder(
    source: Path,
    output: Path,
    preprocessed: Path,
    manifest_path: Path,
    image_paths: list[Path],
    preset: RawImagePreset,
) -> dict[str, object]:
    values = calibration_latents(image_paths, preset)
    reader = LatentReader(values)
    preprocessed.parent.mkdir(parents=True, exist_ok=True)
    model_changed = qnn_preprocess_model(source, preprocessed)
    quantization_input = preprocessed if model_changed else source
    config = get_qnn_qdq_config(
        quantization_input,
        reader,
        activation_type=QuantType.QUInt16,
        weight_type=QuantType.QUInt16,
        calibration_providers=["CPUExecutionProvider"],
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    quantize(quantization_input, output, config)

    reference = ort.InferenceSession(str(source), providers=["CPUExecutionProvider"])
    candidate = ort.InferenceSession(str(output), providers=["CPUExecutionProvider"])
    parity_psnr = []
    maximum_errors = []
    for latent in values:
        expected = np.clip(reference.run(None, {"latent": latent})[0], 0, 1)
        actual = np.clip(candidate.run(None, {"latent": latent})[0], 0, 1)
        parity_psnr.append(array_psnr(expected, actual))
        maximum_errors.append(float(np.max(np.abs(expected - actual))))

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "preset_code": preset.code,
            "raw_payload_max_bytes": preset.maximum_bytes,
            "quantized_onnx_path": str(output.resolve()),
            "quantized_onnx_sha256": file_sha256(output),
            "quantization": {
                "format": "QDQ",
                "activation_type": "QUInt16",
                "weight_type": "QUInt16",
                "calibration_method": "MinMax",
                "calibration_images": [path.name for path in image_paths],
                "calibration_detail_levels": list(preset.detail_levels),
                "preprocessed_model_changed": model_changed,
            },
            "cpu_quantized_parity": {
                "minimum_psnr_db": min(parity_psnr),
                "mean_psnr_db": statistics.fmean(parity_psnr),
                "maximum_absolute_error": max(maximum_errors),
                "passed_35_db_gate": min(parity_psnr) >= 35.0,
            },
        }
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    artifact_dir = generated_artifact_dir()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=artifact_dir / "raw_image_decoder_fp32.onnx"
    )
    parser.add_argument(
        "--output", type=Path, default=artifact_dir / "raw_image_decoder_qdq.onnx"
    )
    parser.add_argument(
        "--preprocessed",
        type=Path,
        default=artifact_dir / "raw_image_decoder_preprocessed.onnx",
    )
    parser.add_argument(
        "--local-manifest",
        type=Path,
        default=artifact_dir / "raw_image_decoder.manifest.json",
    )
    parser.add_argument(
        "--demo-manifest", type=Path, default=PROJECT_ROOT / "data/demo_manifest.json"
    )
    parser.add_argument(
        "--image-dir",
        type=Path,
        default=PROJECT_ROOT / "data/generated/demo-images",
    )
    parser.add_argument(
        "--preset",
        choices=(RAW_IMAGE_PRESET, *(item.code for item in RAW_IMAGE_PRESETS)),
        default=RAW_IMAGE_PRESET,
    )
    args = parser.parse_args()
    preset = parse_raw_image_preset(args.preset)
    result = quantize_decoder(
        args.source.resolve(),
        args.output.resolve(),
        args.preprocessed.resolve(),
        args.local_manifest.resolve(),
        load_acceptance_images(args.demo_manifest, args.image_dir),
        preset,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
