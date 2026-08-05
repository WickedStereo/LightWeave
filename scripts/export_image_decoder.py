"""Export and validate the fixed-shape CompressAI image synthesis graph."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightweave.image import load_image_model  # noqa: E402
from lightweave.paths import generated_artifact_dir  # noqa: E402


class SynthesisWrapper(torch.nn.Module):
    def __init__(self, synthesis: torch.nn.Module) -> None:
        super().__init__()
        self.synthesis = synthesis

    def forward(self, latent: torch.Tensor) -> torch.Tensor:
        return self.synthesis(latent)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def export_decoder(output: Path, weights: Path | None) -> dict[str, object]:
    model, weight_path, weight_hash = load_image_model(weights)
    wrapper = SynthesisWrapper(model.g_s).eval()
    generator = torch.Generator().manual_seed(20260805)
    latent = torch.randn((1, 192, 16, 16), generator=generator)

    output.parent.mkdir(parents=True, exist_ok=True)
    with torch.inference_mode():
        torch_reference = wrapper(latent).cpu().numpy()
        torch.onnx.export(
            wrapper,
            (latent,),
            output,
            input_names=["latent"],
            output_names=["image"],
            opset_version=18,
            do_constant_folding=True,
            dynamo=False,
        )

    graph = onnx.load(output)
    onnx.checker.check_model(graph)
    session = ort.InferenceSession(
        str(output), providers=["CPUExecutionProvider"]
    )
    ort_output = session.run(None, {"latent": latent.numpy()})[0]
    absolute = np.abs(torch_reference - ort_output)
    max_absolute_error = float(absolute.max())
    mean_absolute_error = float(absolute.mean())
    if not np.allclose(torch_reference, ort_output, rtol=1e-3, atol=1e-4):
        raise RuntimeError(
            "CPU ONNX output failed parity with PyTorch: "
            f"max_abs={max_absolute_error}, mean_abs={mean_absolute_error}."
        )

    return {
        "schema_version": 1,
        "source_weights": str(weight_path),
        "source_weights_sha256": weight_hash.hex(),
        "onnx_path": str(output.resolve()),
        "onnx_sha256": file_sha256(output),
        "opset": 18,
        "input_name": "latent",
        "input_shape": [1, 192, 16, 16],
        "output_name": "image",
        "output_shape": list(ort_output.shape),
        "cpu_parity": {
            "max_absolute_error": max_absolute_error,
            "mean_absolute_error": mean_absolute_error,
            "rtol": 1e-3,
            "atol": 1e-4,
            "passed": True,
        },
    }


def main() -> None:
    artifact_dir = generated_artifact_dir()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=artifact_dir / "image_decoder_fp32.onnx",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=artifact_dir / "image_decoder.manifest.json",
    )
    parser.add_argument("--weights", type=Path)
    args = parser.parse_args()

    result = export_decoder(args.output.resolve(), args.weights)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
