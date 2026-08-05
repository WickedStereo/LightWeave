"""Quantize the fixed EnCodec convolutional tail for QNN HTP."""

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
import torch.nn.functional as functional
from onnxruntime.quantization import CalibrationDataReader, QuantType, quantize
from onnxruntime.quantization.execution_providers.qnn import (
    get_qnn_qdq_config,
    qnn_preprocess_model,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightweave.audio import (  # noqa: E402
    SAMPLES_PER_CHUNK,
    cpu_prefix_chunks,
    load_audio_model,
    load_wav,
)
from lightweave.metrics import array_psnr  # noqa: E402
from lightweave.paths import generated_artifact_dir  # noqa: E402


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class PrefixReader(CalibrationDataReader):
    def __init__(self, values: list[np.ndarray]) -> None:
        self.values = values
        self.iterator: Any = None
        self.rewind()

    def get_next(self) -> dict[str, np.ndarray] | None:
        return next(self.iterator, None)

    def rewind(self) -> None:
        self.iterator = iter({"prefix": value} for value in self.values)


def calibration_prefixes(audio_path: Path) -> list[np.ndarray]:
    loaded = load_wav(audio_path)
    model, _, _ = load_audio_model()
    chunks = (loaded.target_samples + SAMPLES_PER_CHUNK - 1) // SAMPLES_PER_CHUNK
    padding = chunks * SAMPLES_PER_CHUNK - loaded.target_samples
    waveform = functional.pad(loaded.waveform, (0, padding))
    with torch.inference_mode():
        frames = model.encode(waveform)
        codes = frames[0][0]
        embedding = model.quantizer.decode(codes.transpose(0, 1))
        prefixes, _ = cpu_prefix_chunks(embedding, model)
    if prefixes.shape != (chunks, 32, SAMPLES_PER_CHUNK):
        raise RuntimeError(f"Unexpected calibration prefix shape: {prefixes.shape}.")
    return [
        prefix.unsqueeze(0).cpu().numpy().astype(np.float32, copy=False)
        for prefix in prefixes
    ]


def quantize_tail(
    source: Path,
    output: Path,
    preprocessed: Path,
    manifest_path: Path,
    audio_path: Path,
    weight_type: QuantType,
) -> dict[str, object]:
    values = calibration_prefixes(audio_path)
    reader = PrefixReader(values)
    changed = qnn_preprocess_model(source, preprocessed)
    quantization_input = preprocessed if changed else source
    config = get_qnn_qdq_config(
        quantization_input,
        reader,
        activation_type=QuantType.QUInt16,
        weight_type=weight_type,
        calibration_providers=["CPUExecutionProvider"],
    )
    quantize(quantization_input, output, config)

    reference = ort.InferenceSession(str(source), providers=["CPUExecutionProvider"])
    candidate = ort.InferenceSession(str(output), providers=["CPUExecutionProvider"])
    psnr_values = []
    maximum_errors = []
    for value in values:
        expected = reference.run(None, {"prefix": value})[0]
        actual = candidate.run(None, {"prefix": value})[0]
        psnr_values.append(array_psnr(expected, actual))
        maximum_errors.append(float(np.max(np.abs(expected - actual))))

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "quantized_onnx_path": str(output.resolve()),
            "quantized_onnx_sha256": file_sha256(output),
            "quantization": {
                "format": "QDQ",
                "activation_type": "QUInt16",
                "weight_type": weight_type.name,
                "calibration_method": "MinMax",
                "calibration_audio": audio_path.name,
                "preprocessed_model_changed": changed,
            },
            "cpu_quantized_parity": {
                "minimum_psnr_db": min(psnr_values),
                "mean_psnr_db": statistics.fmean(psnr_values),
                "maximum_absolute_error": max(maximum_errors),
                "passed_35_db_gate": min(psnr_values) >= 35.0,
            },
        }
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    artifacts = generated_artifact_dir()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=artifacts / "audio_tail_fp32.onnx"
    )
    parser.add_argument(
        "--output", type=Path, default=artifacts / "audio_tail_qdq.onnx"
    )
    parser.add_argument(
        "--preprocessed",
        type=Path,
        default=artifacts / "audio_tail_preprocessed.onnx",
    )
    parser.add_argument(
        "--manifest", type=Path, default=artifacts / "audio_tail.manifest.json"
    )
    parser.add_argument(
        "--audio",
        type=Path,
        default=PROJECT_ROOT / "data/generated/demo-audio/chirp-and-tones.wav",
    )
    parser.add_argument(
        "--weight-type", choices=("uint8", "uint16"), default="uint8"
    )
    args = parser.parse_args()
    result = quantize_tail(
        args.source.resolve(),
        args.output.resolve(),
        args.preprocessed.resolve(),
        args.manifest.resolve(),
        args.audio.resolve(),
        QuantType.QUInt8
        if args.weight_type == "uint8"
        else QuantType.QUInt16,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
