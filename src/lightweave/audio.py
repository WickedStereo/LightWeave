"""EnCodec audio payload generation and CPU/hybrid reconstruction."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import types
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Literal

import numpy as np

from .envelope import (
    AudioMetadata,
    CodecProfile,
    Envelope,
    MediaType,
    parse_envelope,
)
from .errors import ModelMismatchError
from .image import verify_file_sha256, write_bytes_atomic
from .paths import model_manifest_path, project_root

SAMPLE_RATE = 24_000
SAMPLES_PER_CHUNK = 24_000
FRAMES_PER_CHUNK = 75
CODEBOOK_COUNT = 2
BITS_PER_CODE = 10
BANDWIDTH_KBPS = 1.5
AUDIO_NPU_SPLIT_INDEX = 13

AudioBackend = Literal["cpu", "hybrid-qnn"]


@dataclass(slots=True)
class LoadedAudio:
    waveform: Any
    original_sample_rate: int
    target_samples: int


@dataclass(slots=True)
class EncodedAudio:
    envelope: Envelope
    envelope_bytes: bytes
    encode_seconds: float


@dataclass(slots=True)
class DecodedAudio:
    waveform: Any
    backend: AudioBackend
    codebook_seconds: float
    cpu_prefix_seconds: float
    reconstruction_seconds: float
    evidence: dict[str, Any]


def _manifest() -> dict[str, Any]:
    return json.loads(model_manifest_path().read_text(encoding="utf-8"))


def audio_weight_record() -> dict[str, str]:
    return _manifest()["audio"]["weights"]


def resolve_audio_weights(explicit: Path | None = None) -> Path:
    record = audio_weight_record()
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    configured = os.environ.get("LIGHTWEAVE_AUDIO_WEIGHTS")
    if configured:
        candidates.append(Path(configured).expanduser())
    model_dir = os.environ.get("LIGHTWEAVE_MODEL_DIR")
    if model_dir:
        candidates.append(Path(model_dir).expanduser() / record["filename"])
    candidates.append(project_root() / "models" / "weights" / record["filename"])
    candidates.append(
        Path.home() / ".cache" / "torch" / "hub" / "checkpoints" / record["filename"]
    )
    for candidate in candidates:
        if candidate.is_file():
            verify_file_sha256(candidate, record["sha256"])
            return candidate.resolve()
    raise FileNotFoundError(
        "The pinned EnCodec weights are unavailable. Run "
        "`python scripts/prepare_models.py` during setup."
    )


def _encodec_model_class() -> Any:
    # Meta EnCodec imports torchaudio for optional file I/O even though the neural
    # model itself does not use it. LightWeave supplies tested PCM WAV I/O because
    # no torchaudio release matches the pinned PyTorch build on this Windows host.
    if "torchaudio" not in sys.modules:
        try:
            __import__("torchaudio")
        except ModuleNotFoundError:
            sys.modules["torchaudio"] = types.ModuleType("torchaudio")
    from encodec import EncodecModel

    return EncodecModel


def load_audio_model(weights_path: Path | None = None) -> tuple[Any, Path, bytes]:
    resolved = resolve_audio_weights(weights_path)
    fingerprint = verify_file_sha256(resolved, audio_weight_record()["sha256"])
    model_class = _encodec_model_class()
    model = model_class.encodec_model_24khz(
        pretrained=True, repository=resolved.parent
    )
    model.set_target_bandwidth(BANDWIDTH_KBPS)
    model.eval()
    if (
        model.sample_rate != SAMPLE_RATE
        or model.channels != 1
        or model.frame_rate != FRAMES_PER_CHUNK
        or model.quantizer.bins != 1024
    ):
        raise RuntimeError("The loaded EnCodec model does not match profile 0x0201.")
    return model, resolved, fingerprint


def _decode_pcm(value: bytes, sample_width: int) -> np.ndarray:
    if sample_width == 1:
        return (np.frombuffer(value, dtype=np.uint8).astype(np.float32) - 128) / 128
    if sample_width == 2:
        return np.frombuffer(value, dtype="<i2").astype(np.float32) / 32768
    if sample_width == 3:
        raw = np.frombuffer(value, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        integers = raw[:, 0] | (raw[:, 1] << 8) | (raw[:, 2] << 16)
        integers = np.where(integers & 0x800000, integers - 0x1000000, integers)
        return integers.astype(np.float32) / 8_388_608
    if sample_width == 4:
        return np.frombuffer(value, dtype="<i4").astype(np.float32) / 2_147_483_648
    raise ValueError(f"Unsupported PCM WAV sample width: {sample_width} bytes.")


def load_wav(path: Path | BinaryIO) -> LoadedAudio:
    import torch
    import torch.nn.functional as functional

    try:
        wave_source = str(path) if isinstance(path, Path) else path
        with wave.open(wave_source, "rb") as stream:
            if stream.getcomptype() != "NONE":
                raise ValueError("Only uncompressed PCM WAV input is supported.")
            channels = stream.getnchannels()
            if channels not in (1, 2):
                raise ValueError("Audio input must be mono or stereo.")
            sample_rate = stream.getframerate()
            if sample_rate <= 0:
                raise ValueError("Audio input has an invalid sample rate.")
            sample_width = stream.getsampwidth()
            frame_count = stream.getnframes()
            value = stream.readframes(frame_count)
    except wave.Error as exc:
        raise ValueError("Input is not a supported PCM WAV file.") from exc
    samples = _decode_pcm(value, sample_width).reshape(-1, channels)
    mono = samples.mean(axis=1, dtype=np.float32)
    waveform = torch.from_numpy(mono.copy()).view(1, 1, -1)
    if sample_rate != SAMPLE_RATE:
        target_length = max(1, round(waveform.shape[-1] * SAMPLE_RATE / sample_rate))
        waveform = functional.interpolate(
            waveform, size=target_length, mode="linear", align_corners=False
        )
    return LoadedAudio(waveform.contiguous(), sample_rate, waveform.shape[-1])


def write_wav_atomic(waveform: Any, output_path: Path) -> None:
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    array = waveform.detach().cpu().reshape(-1).clamp(-0.999, 0.999).numpy()
    pcm = np.rint(array * 32767.0).astype("<i2").tobytes()
    with tempfile.NamedTemporaryFile(
        prefix=f".{output_path.stem}.",
        suffix=".wav",
        dir=output_path.parent,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with wave.open(str(temporary_path), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(SAMPLE_RATE)
            stream.writeframes(pcm)
        temporary_path.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def pack_codes(codes: Any) -> bytes:
    values = (
        codes.detach()
        .cpu()
        .to(dtype=__import__("torch").int64)
        .squeeze(0)
        .transpose(0, 1)
        .reshape(-1)
        .tolist()
    )
    output = bytearray()
    buffer = 0
    buffered_bits = 0
    for code in values:
        if not 0 <= code < 1024:
            raise ValueError(f"EnCodec index is outside 0..1023: {code}.")
        buffer |= code << buffered_bits
        buffered_bits += BITS_PER_CODE
        while buffered_bits >= 8:
            output.append(buffer & 0xFF)
            buffer >>= 8
            buffered_bits -= 8
    if buffered_bits:
        output.append(buffer & 0xFF)
    return bytes(output)


def unpack_codes(payload: bytes, frame_count: int) -> Any:
    import torch

    count = frame_count * CODEBOOK_COUNT
    expected = (count * BITS_PER_CODE + 7) // 8
    if len(payload) != expected:
        raise ValueError(f"Expected {expected} packed audio bytes, got {len(payload)}.")
    values = np.empty(count, dtype=np.int64)
    buffer = 0
    buffered_bits = 0
    offset = 0
    for byte in payload:
        buffer |= byte << buffered_bits
        buffered_bits += 8
        while buffered_bits >= BITS_PER_CODE and offset < count:
            values[offset] = buffer & 0x3FF
            buffer >>= BITS_PER_CODE
            buffered_bits -= BITS_PER_CODE
            offset += 1
    if offset != count or buffer:
        raise ValueError("Packed audio indices contain invalid trailing bits.")
    tensor = torch.from_numpy(values.reshape(frame_count, CODEBOOK_COUNT).T.copy())
    return tensor.unsqueeze(0)


def encode_audio(
    input_path: Path, *, weights_path: Path | None = None
) -> EncodedAudio:
    import torch
    import torch.nn.functional as functional

    loaded = load_wav(input_path)
    model, _, fingerprint = load_audio_model(weights_path)
    chunk_count = (loaded.target_samples + SAMPLES_PER_CHUNK - 1) // SAMPLES_PER_CHUNK
    padded_samples = chunk_count * SAMPLES_PER_CHUNK
    padding = padded_samples - loaded.target_samples
    waveform = functional.pad(loaded.waveform, (0, padding))
    started = time.perf_counter()
    with torch.inference_mode():
        encoded_frames = model.encode(waveform)
    elapsed = time.perf_counter() - started
    if len(encoded_frames) != 1 or encoded_frames[0][1] is not None:
        raise RuntimeError("Unexpected EnCodec frame or scale structure.")
    codes = encoded_frames[0][0]
    expected_shape = (1, CODEBOOK_COUNT, chunk_count * FRAMES_PER_CHUNK)
    if tuple(codes.shape) != expected_shape:
        raise RuntimeError(f"EnCodec codes {tuple(codes.shape)} != {expected_shape}.")
    payload = pack_codes(codes)
    metadata = AudioMetadata(
        model_sha256=fingerprint,
        sample_rate=SAMPLE_RATE,
        original_samples=loaded.target_samples,
        frame_count=expected_shape[-1],
        padding_samples=padding,
        channels=1,
        codebook_count=CODEBOOK_COUNT,
        bits_per_code=BITS_PER_CODE,
        chunk_frames=FRAMES_PER_CHUNK,
        bandwidth_bps=1_500,
    )
    envelope = Envelope(
        MediaType.AUDIO,
        CodecProfile.ENCODEC_24KHZ_MONO_1P5,
        metadata,
        payload,
    )
    return EncodedAudio(envelope, envelope.to_bytes(), elapsed)


def cpu_prefix_chunks(embedding: Any, model: Any) -> tuple[Any, float]:
    import torch

    decoder_layers = model.decoder.model
    started = time.perf_counter()
    with torch.inference_mode():
        prefix = decoder_layers[:AUDIO_NPU_SPLIT_INDEX](embedding)
        if prefix.shape[1] != 32 or prefix.shape[-1] % SAMPLES_PER_CHUNK:
            raise RuntimeError(f"Unexpected audio NPU prefix shape: {prefix.shape}.")
        chunks = [
            prefix[..., start : start + SAMPLES_PER_CHUNK]
            for start in range(0, prefix.shape[-1], SAMPLES_PER_CHUNK)
        ]
    return torch.cat(chunks, dim=0), time.perf_counter() - started


def cpu_tail_chunks(prefixes: Any, model: Any) -> Any:
    import torch

    tail = model.decoder.model[AUDIO_NPU_SPLIT_INDEX:]
    with torch.inference_mode():
        return torch.cat([tail(prefix.unsqueeze(0)) for prefix in prefixes], dim=0)


def maximum_boundary_jump(waveform: Any) -> float:
    array = waveform.detach().cpu().numpy().reshape(-1)
    maximum = 0.0
    for boundary in range(SAMPLES_PER_CHUNK, len(array), SAMPLES_PER_CHUNK):
        maximum = max(maximum, float(abs(array[boundary] - array[boundary - 1])))
    return maximum


def condition_chunk_boundaries(waveform: Any, correction_samples: int = 480) -> Any:
    """Remove chunk-edge DC steps with a short, decaying CPU correction."""
    import torch

    conditioned = waveform.clone()
    for boundary in range(
        SAMPLES_PER_CHUNK, conditioned.shape[-1], SAMPLES_PER_CHUNK
    ):
        length = min(correction_samples, conditioned.shape[-1] - boundary)
        if length <= 0:
            continue
        difference = conditioned[..., boundary] - conditioned[..., boundary - 1]
        fade = torch.linspace(
            1.0,
            0.0,
            length,
            dtype=conditioned.dtype,
            device=conditioned.device,
        )
        conditioned[..., boundary : boundary + length] -= difference[..., None] * fade
    return conditioned


def decode_audio(
    envelope_or_bytes: Envelope | bytes,
    *,
    backend: AudioBackend,
    output_path: Path | None = None,
    weights_path: Path | None = None,
) -> DecodedAudio:
    import torch

    envelope = (
        parse_envelope(envelope_or_bytes)
        if isinstance(envelope_or_bytes, bytes)
        else envelope_or_bytes
    )
    if not isinstance(envelope.metadata, AudioMetadata):
        raise ValueError("The supplied LightWeave artifact is not audio.")
    model, _, fingerprint = load_audio_model(weights_path)
    if envelope.metadata.model_sha256 != fingerprint:
        raise ModelMismatchError("Audio payload uses incompatible EnCodec weights.")

    codebook_started = time.perf_counter()
    codes = unpack_codes(envelope.payload, envelope.metadata.frame_count)
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
            prefixes,
            source_model_hash=envelope.metadata.model_sha256,
        )
        reconstruction_seconds = time.perf_counter() - started
        raw_waveform = torch.from_numpy(result.output.reshape(1, 1, -1))
        raw_boundary_jump = maximum_boundary_jump(raw_waveform)
        waveform = condition_chunk_boundaries(raw_waveform)
        evidence = result.evidence
        evidence.update(
            {
                "cpu_stages": [
                    "codebook",
                    "decoder-layers-0-through-12",
                ],
                "npu_stages": ["fixed-shape-decoder-layers-13-through-15"],
                "cpu_postprocess": ["480-sample boundary de-click"],
                "raw_maximum_boundary_jump": raw_boundary_jump,
                "conditioned_maximum_boundary_jump": maximum_boundary_jump(waveform),
                "worker_total_seconds": result.elapsed_seconds,
            }
        )
    else:
        raise ValueError(f"Unsupported audio backend: {backend}.")

    waveform = waveform[..., : envelope.metadata.original_samples]
    if not torch.isfinite(waveform).all():
        raise RuntimeError("Decoded audio contains non-finite samples.")
    if output_path is not None:
        write_wav_atomic(waveform, output_path)
    return DecodedAudio(
        waveform,
        backend,
        codebook_seconds,
        prefix_seconds,
        reconstruction_seconds,
        evidence,
    )


def roundtrip_audio(
    input_path: Path,
    *,
    backend: AudioBackend,
    payload_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    from .envelope import envelope_summary
    from .metrics import transfer_estimates

    encoded = encode_audio(input_path)
    write_bytes_atomic(encoded.envelope_bytes, payload_path)
    decoded = decode_audio(
        encoded.envelope_bytes, backend=backend, output_path=output_path
    )
    duration = encoded.envelope.metadata.original_samples / SAMPLE_RATE
    payload_bps = len(encoded.envelope.payload) * 8 / duration
    array = decoded.waveform.detach().cpu().numpy().reshape(-1)
    return {
        **envelope_summary(encoded.envelope),
        **transfer_estimates(len(encoded.envelope_bytes)),
        "backend": backend,
        "duration_seconds": duration,
        "code_payload_bps": payload_bps,
        "encode_seconds": encoded.encode_seconds,
        "codebook_decode_seconds": decoded.codebook_seconds,
        "cpu_prefix_seconds": decoded.cpu_prefix_seconds,
        "reconstruction_seconds": decoded.reconstruction_seconds,
        "restored_samples": int(decoded.waveform.shape[-1]),
        "finite_output": bool(np.isfinite(array).all()),
        "maximum_boundary_jump": maximum_boundary_jump(decoded.waveform),
        "execution_evidence": decoded.evidence,
        "payload_path": str(payload_path.resolve()),
        "output_path": str(output_path.resolve()),
    }
