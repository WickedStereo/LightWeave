"""Evaluate raw payload budgets, determinism, quality, and execution evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightweave.metrics import ms_ssim, psnr, transfer_estimates  # noqa: E402
from lightweave.raw import (  # noqa: E402
    RAW_AUDIO_CHUNK_BYTES,
    RAW_IMAGE_MAX_BYTES,
    decode_raw_audio,
    decode_raw_image,
    encode_raw_audio,
    encode_raw_image,
)


def acceptance_images(manifest_path: Path, image_dir: Path) -> list[Path]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    names = [*manifest["acceptance_images"]]
    names.extend(
        entry["filename"] for entry in manifest.get("analysis_images", [])
    )
    paths = [image_dir / name for name in dict.fromkeys(names)]
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Generated raw acceptance images are missing: "
            + ", ".join(str(path) for path in missing)
        )
    return paths


def evaluate_image(path: Path, backend: str) -> dict[str, object]:
    first = encode_raw_image(path)
    second = encode_raw_image(path)
    if first.payload != second.payload:
        raise RuntimeError(f"Raw image encoding is not deterministic for {path.name}.")
    if len(first.payload) > RAW_IMAGE_MAX_BYTES:
        raise RuntimeError(f"Raw image budget failed for {path.name}.")

    cpu = decode_raw_image(
        first.payload, preset_code=first.preset_code, backend="cpu"
    )
    selected = (
        cpu
        if backend == "cpu"
        else decode_raw_image(
            first.payload, preset_code=first.preset_code, backend="qnn"
        )
    )
    if selected.image.size != (64, 64):
        raise RuntimeError(f"Raw image output size failed for {path.name}.")
    parity = psnr(cpu.image, selected.image)
    if backend == "qnn":
        if parity < 35:
            raise RuntimeError(
                f"Raw image NPU parity failed for {path.name}: {parity}."
            )
        if (
            not selected.evidence.get("strict_no_fallback")
            or selected.evidence.get("profile_cpu_node_count") != 0
        ):
            raise RuntimeError(f"Raw image strict-QNN proof failed for {path.name}.")

    return {
        "name": path.name,
        "raw_bytes": len(first.payload),
        "deterministic": True,
        "effective_detail": first.effective_detail,
        "fallback": first.fallback,
        "psnr_db": psnr(first.reference, selected.image),
        "ms_ssim": ms_ssim(first.reference, selected.image),
        "npu_cpu_parity_psnr_db": parity,
        **transfer_estimates(len(first.payload)),
        "execution_evidence": selected.evidence,
    }


def evaluate_audio(path: Path, backend: str) -> dict[str, object]:
    encoded = encode_raw_audio(path)
    if len(encoded.payload) != encoded.chunk_count * RAW_AUDIO_CHUNK_BYTES:
        raise RuntimeError("Raw audio payload did not contain exact 188-byte chunks.")
    decoded = decode_raw_audio(
        encoded.payload, preset_code=encoded.preset_code, backend=backend
    )
    array = decoded.waveform.detach().cpu().numpy()
    if array.shape[-1] != encoded.original_samples or not np.isfinite(array).all():
        raise RuntimeError("Raw audio output length or finiteness gate failed.")
    if backend == "hybrid-qnn" and (
        not decoded.evidence.get("strict_no_fallback")
        or decoded.evidence.get("profile_cpu_node_count") != 0
    ):
        raise RuntimeError("Raw audio QNN-tail execution proof failed.")
    duration = encoded.original_samples / 24_000
    return {
        "name": path.name,
        "preset_code": encoded.preset_code,
        "raw_bytes": len(encoded.payload),
        "chunk_count": encoded.chunk_count,
        "bytes_per_chunk": RAW_AUDIO_CHUNK_BYTES,
        "restored_samples": int(array.shape[-1]),
        "finite_output": True,
        "code_payload_bps": len(encoded.payload) * 8 / duration,
        "execution_evidence": decoded.evidence,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--demo-manifest", type=Path, default=PROJECT_ROOT / "data/demo_manifest.json"
    )
    parser.add_argument(
        "--image-dir",
        type=Path,
        default=PROJECT_ROOT / "data/generated/demo-images",
    )
    parser.add_argument("--image-backend", choices=("cpu", "qnn"), default="cpu")
    parser.add_argument("--audio", type=Path)
    parser.add_argument(
        "--audio-backend", choices=("cpu", "hybrid-qnn"), default="cpu"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    images = [
        evaluate_image(path, args.image_backend)
        for path in acceptance_images(args.demo_manifest, args.image_dir)
    ]
    result: dict[str, object] = {
        "image_backend": args.image_backend,
        "images": images,
        "all_images_within_128_bytes": all(
            entry["raw_bytes"] <= RAW_IMAGE_MAX_BYTES for entry in images
        ),
    }
    if args.audio:
        result["audio_backend"] = args.audio_backend
        result["audio"] = evaluate_audio(args.audio, args.audio_backend)

    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
