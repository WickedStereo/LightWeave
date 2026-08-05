"""High-level image operations shared by the CLI and dashboard."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
from PIL import Image

from .envelope import ImageMetadata, envelope_summary, parse_envelope
from .image import (
    crop_visible_image,
    encode_image,
    entropy_decode_image,
    reconstruct_image_cpu,
    save_image_atomic,
    tensor_to_padded_image,
)
from .metrics import ms_ssim, psnr, transfer_estimates
from .npu import reconstruct_on_npu

Backend = Literal["cpu", "qnn"]


@dataclass(slots=True)
class ImageDecodeResult:
    padded_image: Image.Image
    visible_image: Image.Image
    entropy_decode_seconds: float
    reconstruction_seconds: float
    backend: Backend
    evidence: dict[str, Any]


def decode_image_bytes(
    value: bytes,
    *,
    backend: Backend,
    output_path: Path | None = None,
    weights_path: Path | None = None,
    arm64_python: Path | None = None,
    decoder_model: Path | None = None,
) -> ImageDecodeResult:
    envelope = parse_envelope(value)
    if not isinstance(envelope.metadata, ImageMetadata):
        raise ValueError("The supplied LightWeave artifact is not an image.")
    decoded, model = entropy_decode_image(envelope, weights_path=weights_path)

    if backend == "cpu":
        tensor, reconstruction_seconds = reconstruct_image_cpu(decoded, model)
        padded = tensor_to_padded_image(tensor)
        evidence: dict[str, Any] = {
            "strict_no_fallback": False,
            "npu_selected": False,
            "backend": "cpu-development-reference",
        }
    elif backend == "qnn":
        started = time.perf_counter()
        npu_result = reconstruct_on_npu(
            decoded.latent,
            source_model_hash=envelope.metadata.model_sha256,
            arm64_python=arm64_python,
            model_path=decoder_model,
        )
        reconstruction_seconds = time.perf_counter() - started
        array = np.clip(npu_result.output[0].transpose(1, 2, 0), 0, 1)
        padded = Image.fromarray(np.rint(array * 255.0).astype(np.uint8))
        evidence = npu_result.evidence
        evidence["worker_total_seconds"] = npu_result.elapsed_seconds
    else:
        raise ValueError(f"Unsupported image backend: {backend}")

    visible = crop_visible_image(padded, envelope.metadata)
    if output_path is not None:
        save_image_atomic(visible, output_path)
    return ImageDecodeResult(
        padded,
        visible,
        decoded.entropy_decode_seconds,
        reconstruction_seconds,
        backend,
        evidence,
    )


def roundtrip_image(
    input_path: Path,
    *,
    backend: Backend,
    payload_path: Path,
    output_path: Path,
    allow_oversize: bool = False,
) -> dict[str, Any]:
    from .image import write_bytes_atomic

    encoded = encode_image(input_path, allow_oversize=allow_oversize)
    write_bytes_atomic(encoded.envelope_bytes, payload_path)
    decoded = decode_image_bytes(
        encoded.envelope_bytes, backend=backend, output_path=output_path
    )
    summary = envelope_summary(encoded.envelope)
    quality_psnr = psnr(encoded.prepared.visible_reference, decoded.visible_image)
    quality_ms_ssim = ms_ssim(
        encoded.prepared.visible_reference, decoded.visible_image
    )
    visible_pixels = (
        encoded.prepared.content_width * encoded.prepared.content_height
    )
    return {
        **summary,
        **transfer_estimates(len(encoded.envelope_bytes)),
        "bits_per_pixel": len(encoded.envelope_bytes) * 8 / visible_pixels,
        "within_2048_byte_budget": len(encoded.envelope_bytes) <= 2048,
        "backend": backend,
        "encode_seconds": encoded.encode_seconds,
        "entropy_decode_seconds": decoded.entropy_decode_seconds,
        "reconstruction_seconds": decoded.reconstruction_seconds,
        "psnr_db": quality_psnr,
        "ms_ssim": quality_ms_ssim,
        "npu_evidence": decoded.evidence,
        "payload_path": str(payload_path.resolve()),
        "output_path": str(output_path.resolve()),
    }
