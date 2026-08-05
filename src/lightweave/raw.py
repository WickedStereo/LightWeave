"""Header-free image and audio codecs for the assumed reliable optical pipe."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Literal

import numpy as np
from PIL import Image, ImageOps

from .audio import (
    CODEBOOK_COUNT,
    FRAMES_PER_CHUNK,
    SAMPLES_PER_CHUNK,
    condition_chunk_boundaries,
    cpu_prefix_chunks,
    load_audio_model,
    load_wav,
    maximum_boundary_jump,
    pack_codes,
    unpack_codes,
    write_wav_atomic,
)
from .image import load_image_model, save_image_atomic, tensor_to_padded_image

RAW_IMAGE_PRESET = "I64-Q1"
RAW_IMAGE_SIZE = 64
RAW_IMAGE_LATENT_SHAPE = (1, 192, 4, 4)
RAW_IMAGE_MAX_BYTES = 128
RAW_IMAGE_DETAIL_LEVELS = (64, 56, 48, 40, 32, 24, 16, 8)

RAW_AUDIO_PRESET_PREFIX = "A1-E15-S"
RAW_AUDIO_CHUNK_BYTES = 188

ImageBackend = Literal["cpu", "qnn"]
AudioBackend = Literal["cpu", "hybrid-qnn"]


@dataclass(slots=True)
class EncodedRawImage:
    payload: bytes
    preset_code: str
    reference: Image.Image
    original_preview: Image.Image
    effective_detail: int
    fallback: str
    encode_seconds: float


@dataclass(slots=True)
class DecodedRawImage:
    image: Image.Image
    backend: ImageBackend
    entropy_decode_seconds: float
    reconstruction_seconds: float
    evidence: dict[str, Any]


@dataclass(slots=True)
class EncodedRawAudio:
    payload: bytes
    preset_code: str
    original_samples: int
    chunk_count: int
    encode_seconds: float


@dataclass(slots=True)
class DecodedRawAudio:
    waveform: Any
    backend: AudioBackend
    codebook_seconds: float
    cpu_prefix_seconds: float
    reconstruction_seconds: float
    evidence: dict[str, Any]


def parse_raw_image_preset(code: str) -> str:
    if code != RAW_IMAGE_PRESET:
        raise ValueError(
            f"Unsupported raw image preset {code!r}; expected {RAW_IMAGE_PRESET}."
        )
    return code


def raw_audio_preset(original_samples: int) -> str:
    if original_samples <= 0:
        raise ValueError("Raw audio must contain at least one sample.")
    return f"{RAW_AUDIO_PRESET_PREFIX}{original_samples}"


def parse_raw_audio_preset(code: str) -> int:
    match = re.fullmatch(r"A1-E15-S([1-9][0-9]*)", code)
    if match is None:
        raise ValueError(
            "Malformed raw audio preset; expected A1-E15-S followed by the exact "
            "positive 24 kHz sample count."
        )
    return int(match.group(1))


def _open_raw_image(path: Path | BinaryIO) -> Image.Image:
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    if image.width <= 0 or image.height <= 0:
        raise ValueError("Input image has invalid dimensions.")
    return image


def _letterbox(image: Image.Image, size: int) -> Image.Image:
    scale = min(size / image.width, size / image.height)
    width = max(1, min(size, round(image.width * scale)))
    height = max(1, min(size, round(image.height * scale)))
    visible = image.resize((width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (size, size), (0, 0, 0))
    canvas.paste(visible, ((size - width) // 2, (size - height) // 2))
    return canvas


def raw_image_candidate(image: Image.Image, detail: int) -> Image.Image:
    if detail not in RAW_IMAGE_DETAIL_LEVELS:
        raise ValueError(f"Unsupported raw image detail level: {detail}.")
    candidate = _letterbox(image, detail)
    if detail != RAW_IMAGE_SIZE:
        candidate = candidate.resize(
            (RAW_IMAGE_SIZE, RAW_IMAGE_SIZE), Image.Resampling.NEAREST
        )
    return candidate


def _image_tensor(image: Image.Image) -> Any:
    import torch

    array = np.asarray(image, dtype=np.float32) / 255.0
    return torch.from_numpy(array).permute(2, 0, 1).unsqueeze(0).contiguous()


def _compress_raw_image(model: Any, image: Image.Image) -> bytes:
    import torch

    with torch.inference_mode():
        compressed = model.compress(_image_tensor(image))
    strings = compressed.get("strings")
    shape = compressed.get("shape")
    if (
        not isinstance(strings, list)
        or len(strings) != 1
        or not isinstance(strings[0], list)
        or len(strings[0]) != 1
        or not isinstance(strings[0][0], bytes)
    ):
        raise RuntimeError("Raw image compression did not return one entropy string.")
    if tuple(int(value) for value in shape) != (4, 4):
        raise RuntimeError(f"Raw image latent shape must be [4,4], got {shape!r}.")
    if int(model.entropy_bottleneck.channels) != 192:
        raise RuntimeError("Raw image model must expose 192 entropy channels.")
    return strings[0][0]


def encode_raw_image(
    input_path: Path | BinaryIO, *, weights_path: Path | None = None
) -> EncodedRawImage:
    image = _open_raw_image(input_path)
    model, _, _ = load_image_model(weights_path)
    started = time.perf_counter()
    for detail in RAW_IMAGE_DETAIL_LEVELS:
        candidate = raw_image_candidate(image, detail)
        payload = _compress_raw_image(model, candidate)
        if len(payload) <= RAW_IMAGE_MAX_BYTES:
            return EncodedRawImage(
                payload,
                RAW_IMAGE_PRESET,
                candidate,
                image,
                detail,
                "none",
                time.perf_counter() - started,
            )

    mean = tuple(
        int(round(value))
        for value in np.asarray(image, dtype=np.float32).mean(axis=(0, 1))
    )
    for fallback, color in (("mean-color", mean), ("black", (0, 0, 0))):
        candidate = Image.new("RGB", (RAW_IMAGE_SIZE, RAW_IMAGE_SIZE), color)
        payload = _compress_raw_image(model, candidate)
        if len(payload) <= RAW_IMAGE_MAX_BYTES:
            return EncodedRawImage(
                payload,
                RAW_IMAGE_PRESET,
                candidate,
                image,
                0,
                fallback,
                time.perf_counter() - started,
            )
    raise RuntimeError(
        "The deterministic black fallback exceeded the 128-byte raw image contract."
    )


def decode_raw_image(
    payload: bytes,
    *,
    preset_code: str,
    backend: ImageBackend,
    output_path: Path | None = None,
    weights_path: Path | None = None,
    arm64_python: Path | None = None,
    decoder_model: Path | None = None,
) -> DecodedRawImage:
    import torch

    parse_raw_image_preset(preset_code)
    if not payload:
        raise ValueError("Raw image payload is empty.")
    if len(payload) > RAW_IMAGE_MAX_BYTES:
        raise ValueError(
            f"Raw image payload is {len(payload)} bytes; maximum is 128 bytes."
        )
    model, _, fingerprint = load_image_model(weights_path)
    started = time.perf_counter()
    try:
        with torch.inference_mode():
            latent = model.entropy_bottleneck.decompress([payload], (4, 4))
    except Exception as exc:
        raise ValueError("Raw image entropy stream could not be decoded.") from exc
    entropy_seconds = time.perf_counter() - started
    if tuple(latent.shape) != RAW_IMAGE_LATENT_SHAPE:
        raise RuntimeError(
            f"Raw image latent shape {tuple(latent.shape)} != "
            f"{RAW_IMAGE_LATENT_SHAPE}."
        )

    if backend == "cpu":
        started = time.perf_counter()
        with torch.inference_mode():
            reconstructed = model.g_s(latent).clamp_(0, 1)
        reconstruction_seconds = time.perf_counter() - started
        evidence: dict[str, Any] = {
            "backend": "cpu-reference",
            "strict_no_fallback": False,
            "input_shape": list(latent.shape),
            "output_shape": list(reconstructed.shape),
        }
    elif backend == "qnn":
        from .npu import default_raw_decoder_model, reconstruct_on_npu

        started = time.perf_counter()
        result = reconstruct_on_npu(
            latent,
            source_model_hash=fingerprint,
            arm64_python=arm64_python,
            model_path=decoder_model or default_raw_decoder_model(),
            manifest_path=None,
            raw_image=True,
        )
        reconstruction_seconds = time.perf_counter() - started
        reconstructed = torch.from_numpy(result.output).clamp_(0, 1)
        evidence = result.evidence
        evidence["worker_total_seconds"] = result.elapsed_seconds
    else:
        raise ValueError(f"Unsupported raw image backend: {backend}.")

    if tuple(reconstructed.shape) != (1, 3, RAW_IMAGE_SIZE, RAW_IMAGE_SIZE):
        raise RuntimeError(
            f"Raw image reconstruction has unexpected shape {reconstructed.shape}."
        )
    image = tensor_to_padded_image(reconstructed)
    if output_path is not None:
        save_image_atomic(image, output_path)
    return DecodedRawImage(
        image,
        backend,
        entropy_seconds,
        reconstruction_seconds,
        evidence,
    )


def pack_raw_audio_chunks(codes: Any) -> bytes:
    shape = tuple(int(value) for value in codes.shape)
    if len(shape) != 3 or shape[:2] != (1, CODEBOOK_COUNT):
        raise ValueError(f"Unexpected EnCodec code shape: {shape}.")
    if shape[-1] <= 0 or shape[-1] % FRAMES_PER_CHUNK:
        raise ValueError("Raw audio codes must contain whole 75-frame chunks.")
    chunks = []
    for start in range(0, shape[-1], FRAMES_PER_CHUNK):
        packed = pack_codes(codes[..., start : start + FRAMES_PER_CHUNK])
        if len(packed) != RAW_AUDIO_CHUNK_BYTES or packed[-1] & 0xF0:
            raise RuntimeError("Raw audio chunk violates the 1,500-bit contract.")
        chunks.append(packed)
    return b"".join(chunks)


def unpack_raw_audio_chunks(payload: bytes) -> Any:
    import torch

    if not payload:
        raise ValueError("Raw audio payload is empty.")
    if len(payload) % RAW_AUDIO_CHUNK_BYTES:
        raise ValueError("Raw audio payload size must be divisible by 188 bytes.")
    chunks = []
    for offset in range(0, len(payload), RAW_AUDIO_CHUNK_BYTES):
        chunk = payload[offset : offset + RAW_AUDIO_CHUNK_BYTES]
        if chunk[-1] & 0xF0:
            raise ValueError("Raw audio chunk has non-zero padding bits.")
        chunks.append(unpack_codes(chunk, FRAMES_PER_CHUNK))
    return torch.cat(chunks, dim=-1)


def encode_raw_audio(
    input_path: Path | BinaryIO, *, weights_path: Path | None = None
) -> EncodedRawAudio:
    import torch
    import torch.nn.functional as functional

    loaded = load_wav(input_path)
    if loaded.target_samples <= 0:
        raise ValueError("Raw audio input is empty.")
    model, _, _ = load_audio_model(weights_path)
    chunk_count = (
        loaded.target_samples + SAMPLES_PER_CHUNK - 1
    ) // SAMPLES_PER_CHUNK
    padding = chunk_count * SAMPLES_PER_CHUNK - loaded.target_samples
    waveform = functional.pad(loaded.waveform, (0, padding))
    started = time.perf_counter()
    with torch.inference_mode():
        encoded_frames = model.encode(waveform)
    encode_seconds = time.perf_counter() - started
    if len(encoded_frames) != 1 or encoded_frames[0][1] is not None:
        raise RuntimeError("Unexpected EnCodec frame or scale structure.")
    codes = encoded_frames[0][0]
    expected = (1, CODEBOOK_COUNT, chunk_count * FRAMES_PER_CHUNK)
    if tuple(codes.shape) != expected:
        raise RuntimeError(f"EnCodec codes {tuple(codes.shape)} != {expected}.")
    payload = pack_raw_audio_chunks(codes)
    return EncodedRawAudio(
        payload,
        raw_audio_preset(loaded.target_samples),
        loaded.target_samples,
        chunk_count,
        encode_seconds,
    )


def decode_raw_audio(
    payload: bytes,
    *,
    preset_code: str,
    backend: AudioBackend,
    output_path: Path | None = None,
    weights_path: Path | None = None,
) -> DecodedRawAudio:
    import torch

    original_samples = parse_raw_audio_preset(preset_code)
    if not payload:
        raise ValueError("Raw audio payload is empty.")
    if len(payload) % RAW_AUDIO_CHUNK_BYTES:
        raise ValueError("Raw audio payload size must be divisible by 188 bytes.")
    chunk_count = len(payload) // RAW_AUDIO_CHUNK_BYTES
    minimum_samples = (chunk_count - 1) * SAMPLES_PER_CHUNK + 1
    maximum_samples = chunk_count * SAMPLES_PER_CHUNK
    if not minimum_samples <= original_samples <= maximum_samples:
        raise ValueError(
            f"Preset sample count {original_samples} is impossible for "
            f"{chunk_count} raw audio chunks."
        )

    model, _, fingerprint = load_audio_model(weights_path)
    codebook_started = time.perf_counter()
    codes = unpack_raw_audio_chunks(payload)
    with torch.inference_mode():
        embedding = model.quantizer.decode(codes.transpose(0, 1))
    codebook_seconds = time.perf_counter() - codebook_started

    if backend == "cpu":
        started = time.perf_counter()
        with torch.inference_mode():
            waveform = model.decoder(embedding)
        reconstruction_seconds = time.perf_counter() - started
        prefix_seconds = 0.0
        evidence: dict[str, Any] = {
            "backend": "cpu-reference",
            "cpu_stages": ["codebook", "initial-convolution", "lstm", "tail"],
            "npu_stages": [],
            "strict_no_fallback": False,
        }
    elif backend == "hybrid-qnn":
        from .audio_npu import reconstruct_audio_tail_on_npu

        prefixes, prefix_seconds = cpu_prefix_chunks(embedding, model)
        started = time.perf_counter()
        result = reconstruct_audio_tail_on_npu(
            prefixes, source_model_hash=fingerprint
        )
        reconstruction_seconds = time.perf_counter() - started
        raw_waveform = torch.from_numpy(result.output.reshape(1, 1, -1))
        raw_jump = maximum_boundary_jump(raw_waveform)
        waveform = condition_chunk_boundaries(raw_waveform)
        evidence = result.evidence
        evidence.update(
            {
                "cpu_stages": ["codebook", "decoder-layers-0-through-12"],
                "npu_stages": ["fixed-shape-decoder-layers-13-through-15"],
                "cpu_postprocess": ["480-sample boundary de-click"],
                "raw_maximum_boundary_jump": raw_jump,
                "conditioned_maximum_boundary_jump": maximum_boundary_jump(
                    waveform
                ),
                "worker_total_seconds": result.elapsed_seconds,
            }
        )
    else:
        raise ValueError(f"Unsupported raw audio backend: {backend}.")

    waveform = waveform[..., :original_samples]
    if tuple(waveform.shape) != (1, 1, original_samples):
        raise RuntimeError(f"Decoded audio has unexpected shape {waveform.shape}.")
    if not torch.isfinite(waveform).all():
        raise RuntimeError("Decoded raw audio contains non-finite samples.")
    if output_path is not None:
        write_wav_atomic(waveform, output_path)
    return DecodedRawAudio(
        waveform,
        backend,
        codebook_seconds,
        prefix_seconds,
        reconstruction_seconds,
        evidence,
    )
