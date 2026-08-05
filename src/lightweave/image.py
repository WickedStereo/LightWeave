"""CompressAI image preparation, entropy coding, and reconstruction."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from .envelope import (
    CodecProfile,
    ColorSpace,
    Envelope,
    ImageMetadata,
    MediaType,
    parse_envelope,
)
from .errors import ModelMismatchError, PayloadTooLargeError
from .paths import model_manifest_path, project_root

IMAGE_SIZE = 256
DEFAULT_MAX_ENVELOPE_BYTES = 2048


@dataclass(slots=True)
class PreparedImage:
    tensor: Any
    visible_reference: Image.Image
    original_width: int
    original_height: int
    content_width: int
    content_height: int
    pad_left: int
    pad_top: int
    pad_right: int
    pad_bottom: int


@dataclass(slots=True)
class EncodedImage:
    envelope: Envelope
    envelope_bytes: bytes
    prepared: PreparedImage
    encode_seconds: float


@dataclass(slots=True)
class DecodedLatent:
    envelope: Envelope
    latent: Any
    entropy_decode_seconds: float


def _manifest() -> dict[str, Any]:
    return json.loads(model_manifest_path().read_text(encoding="utf-8"))


def image_weight_record() -> dict[str, str]:
    return _manifest()["image"]["weights"]


def resolve_image_weights(explicit: Path | None = None) -> Path:
    record = image_weight_record()
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    configured_file = os.environ.get("LIGHTWEAVE_IMAGE_WEIGHTS")
    if configured_file:
        candidates.append(Path(configured_file).expanduser())
    configured_dir = os.environ.get("LIGHTWEAVE_MODEL_DIR")
    if configured_dir:
        candidates.append(Path(configured_dir).expanduser() / record["filename"])
    candidates.append(project_root() / "models" / "weights" / record["filename"])
    candidates.append(
        Path.home() / ".cache" / "torch" / "hub" / "checkpoints" / record["filename"]
    )

    for candidate in candidates:
        if candidate.is_file():
            verify_file_sha256(candidate, record["sha256"])
            return candidate.resolve()
    searched = "\n  - ".join(str(path) for path in candidates)
    raise FileNotFoundError(
        "The pinned CompressAI weights are unavailable. Run "
        "`python scripts/prepare_models.py` during setup. Searched:\n  - "
        f"{searched}"
    )


def verify_file_sha256(path: Path, expected_hex: str) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if actual.lower() != expected_hex.lower():
        raise ModelMismatchError(
            f"SHA-256 mismatch for {path.name}: expected {expected_hex}, got {actual}."
        )
    return digest.digest()


def load_image_model(weights_path: Path | None = None) -> tuple[Any, Path, bytes]:
    import torch
    from compressai.zoo import bmshj2018_factorized
    from compressai.zoo.pretrained import load_pretrained

    resolved = resolve_image_weights(weights_path)
    fingerprint = verify_file_sha256(resolved, image_weight_record()["sha256"])
    state_dict = torch.load(
        resolved, map_location="cpu", weights_only=True
    )
    state_dict = load_pretrained(state_dict)
    model = bmshj2018_factorized(quality=1, pretrained=False)
    model.load_state_dict(state_dict)
    model.eval()
    return model, resolved, fingerprint


def prepare_image(path: Path) -> PreparedImage:
    import torch

    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    original_width, original_height = image.size
    if original_width <= 0 or original_height <= 0:
        raise ValueError("Input image has invalid dimensions.")

    scale = min(IMAGE_SIZE / original_width, IMAGE_SIZE / original_height)
    content_width = max(1, min(IMAGE_SIZE, round(original_width * scale)))
    content_height = max(1, min(IMAGE_SIZE, round(original_height * scale)))
    visible = image.resize((content_width, content_height), Image.Resampling.LANCZOS)

    horizontal_padding = IMAGE_SIZE - content_width
    vertical_padding = IMAGE_SIZE - content_height
    pad_left = horizontal_padding // 2
    pad_right = horizontal_padding - pad_left
    pad_top = vertical_padding // 2
    pad_bottom = vertical_padding - pad_top

    padded = ImageOps.expand(
        visible,
        border=(pad_left, pad_top, pad_right, pad_bottom),
        fill=(0, 0, 0),
    )
    array = np.asarray(padded, dtype=np.float32) / 255.0
    tensor = torch.from_numpy(array).permute(2, 0, 1).unsqueeze(0).contiguous()
    return PreparedImage(
        tensor=tensor,
        visible_reference=visible,
        original_width=original_width,
        original_height=original_height,
        content_width=content_width,
        content_height=content_height,
        pad_left=pad_left,
        pad_top=pad_top,
        pad_right=pad_right,
        pad_bottom=pad_bottom,
    )


def encode_image(
    input_path: Path,
    *,
    weights_path: Path | None = None,
    max_envelope_bytes: int = DEFAULT_MAX_ENVELOPE_BYTES,
    allow_oversize: bool = False,
) -> EncodedImage:
    import torch

    model, _, fingerprint = load_image_model(weights_path)
    prepared = prepare_image(input_path)
    started = time.perf_counter()
    with torch.inference_mode():
        compressed = model.compress(prepared.tensor)
    encode_seconds = time.perf_counter() - started

    strings = compressed.get("strings")
    shape = compressed.get("shape")
    if (
        not isinstance(strings, list)
        or len(strings) != 1
        or not isinstance(strings[0], list)
        or len(strings[0]) != 1
        or not isinstance(strings[0][0], bytes)
    ):
        raise RuntimeError(
            "The selected image profile did not return one entropy string."
        )
    if len(shape) != 2:
        raise RuntimeError(f"Unexpected CompressAI latent shape metadata: {shape!r}")
    latent_height, latent_width = (int(shape[0]), int(shape[1]))
    latent_channels = int(model.entropy_bottleneck.channels)
    if (latent_channels, latent_height, latent_width) != (192, 16, 16):
        raise RuntimeError(
            "The loaded model does not match the fixed LightWeave image profile: "
            f"got {(latent_channels, latent_height, latent_width)!r}."
        )

    metadata = ImageMetadata(
        model_sha256=fingerprint,
        original_width=prepared.original_width,
        original_height=prepared.original_height,
        content_width=prepared.content_width,
        content_height=prepared.content_height,
        pad_left=prepared.pad_left,
        pad_top=prepared.pad_top,
        pad_right=prepared.pad_right,
        pad_bottom=prepared.pad_bottom,
        latent_channels=latent_channels,
        latent_height=latent_height,
        latent_width=latent_width,
        quality=1,
        color_space=ColorSpace.RGB,
    )
    envelope = Envelope(
        MediaType.IMAGE,
        CodecProfile.BMSHJ2018_FACTORIZED_Q1,
        metadata,
        strings[0][0],
    )
    value = envelope.to_bytes()
    if len(value) > max_envelope_bytes and not allow_oversize:
        raise PayloadTooLargeError(
            f"The encoded envelope is {len(value)} bytes; the configured ceiling is "
            f"{max_envelope_bytes} bytes. Use --allow-oversize only for analysis."
        )
    return EncodedImage(envelope, value, prepared, encode_seconds)


def entropy_decode_image(
    envelope_or_bytes: Envelope | bytes,
    *,
    weights_path: Path | None = None,
) -> tuple[DecodedLatent, Any]:
    import torch

    envelope = (
        parse_envelope(envelope_or_bytes)
        if isinstance(envelope_or_bytes, bytes)
        else envelope_or_bytes
    )
    if not isinstance(envelope.metadata, ImageMetadata):
        raise ValueError("The supplied envelope is not an image.")
    model, _, fingerprint = load_image_model(weights_path)
    if envelope.metadata.model_sha256 != fingerprint:
        raise ModelMismatchError(
            "The image envelope was encoded with different model weights."
        )
    started = time.perf_counter()
    with torch.inference_mode():
        latent = model.entropy_bottleneck.decompress(
            [envelope.payload],
            (envelope.metadata.latent_height, envelope.metadata.latent_width),
        )
    elapsed = time.perf_counter() - started
    expected = (
        1,
        envelope.metadata.latent_channels,
        envelope.metadata.latent_height,
        envelope.metadata.latent_width,
    )
    if tuple(latent.shape) != expected:
        raise RuntimeError(f"Decoded latent shape {tuple(latent.shape)} != {expected}.")
    return DecodedLatent(envelope, latent, elapsed), model


def reconstruct_image_cpu(decoded: DecodedLatent, model: Any) -> tuple[Any, float]:
    import torch

    started = time.perf_counter()
    with torch.inference_mode():
        reconstructed = model.g_s(decoded.latent).clamp_(0, 1)
    return reconstructed, time.perf_counter() - started


def tensor_to_padded_image(tensor: Any) -> Image.Image:
    array = (
        tensor.detach()
        .cpu()
        .squeeze(0)
        .permute(1, 2, 0)
        .clamp(0, 1)
        .numpy()
    )
    return Image.fromarray(np.rint(array * 255.0).astype(np.uint8), mode="RGB")


def crop_visible_image(image: Image.Image, metadata: ImageMetadata) -> Image.Image:
    return image.crop(
        (
            metadata.pad_left,
            metadata.pad_top,
            metadata.pad_left + metadata.content_width,
            metadata.pad_top + metadata.content_height,
        )
    )


def save_image_atomic(image: Image.Image, output_path: Path) -> None:
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = output_path.suffix or ".png"
    with tempfile.NamedTemporaryFile(
        prefix=f".{output_path.stem}.",
        suffix=suffix,
        dir=output_path.parent,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        image.save(temporary_path)
        temporary_path.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def write_bytes_atomic(value: bytes, output_path: Path) -> None:
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{output_path.name}.", dir=output_path.parent, delete=False
    ) as temporary:
        temporary.write(value)
        temporary_path = Path(temporary.name)
    try:
        temporary_path.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
