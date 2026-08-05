"""Versioned LightWeave binary media envelope."""

from __future__ import annotations

import hashlib
import io
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import BinaryIO

from .errors import EnvelopeError, IntegrityError

MAGIC = b"LWV1"
FORMAT_VERSION = 1
MAX_METADATA_BYTES = 4096
MAX_PAYLOAD_BYTES = 128 * 1024 * 1024
SUPPORTED_FLAGS = 0

COMMON_HEADER = struct.Struct("<4sBBHHHI32s")
IMAGE_METADATA_STRUCT = struct.Struct("<32s11H2B")
AUDIO_METADATA_STRUCT = struct.Struct("<32sIIIIBBBHH")


class MediaType(IntEnum):
    IMAGE = 1
    AUDIO = 2


class CodecProfile(IntEnum):
    BMSHJ2018_FACTORIZED_Q1 = 0x0101
    ENCODEC_24KHZ_MONO_1P5 = 0x0201


class ColorSpace(IntEnum):
    RGB = 1


@dataclass(frozen=True, slots=True)
class ImageMetadata:
    model_sha256: bytes
    original_width: int
    original_height: int
    content_width: int
    content_height: int
    pad_left: int
    pad_top: int
    pad_right: int
    pad_bottom: int
    latent_channels: int
    latent_height: int
    latent_width: int
    quality: int = 1
    color_space: ColorSpace = ColorSpace.RGB

    def __post_init__(self) -> None:
        _validate_hash(self.model_sha256, "model_sha256")
        values = (
            self.original_width,
            self.original_height,
            self.content_width,
            self.content_height,
            self.latent_channels,
            self.latent_height,
            self.latent_width,
        )
        if any(value <= 0 or value > 0xFFFF for value in values):
            raise EnvelopeError("Image and latent dimensions must be 1..65535.")
        pads = (self.pad_left, self.pad_top, self.pad_right, self.pad_bottom)
        if any(value < 0 or value > 0xFFFF for value in pads):
            raise EnvelopeError("Image padding must be 0..65535.")
        if self.content_width + self.pad_left + self.pad_right != 256:
            raise EnvelopeError(
                "Horizontal image metadata does not describe 256 pixels."
            )
        if self.content_height + self.pad_top + self.pad_bottom != 256:
            raise EnvelopeError("Vertical image metadata does not describe 256 pixels.")
        if not 1 <= self.quality <= 255:
            raise EnvelopeError("Image quality must fit in one positive byte.")

    def to_bytes(self) -> bytes:
        return IMAGE_METADATA_STRUCT.pack(
            self.model_sha256,
            self.original_width,
            self.original_height,
            self.content_width,
            self.content_height,
            self.pad_left,
            self.pad_top,
            self.pad_right,
            self.pad_bottom,
            self.latent_channels,
            self.latent_height,
            self.latent_width,
            self.quality,
            int(self.color_space),
        )

    @classmethod
    def from_bytes(cls, value: bytes) -> ImageMetadata:
        if len(value) != IMAGE_METADATA_STRUCT.size:
            raise EnvelopeError(
                f"Image metadata must be {IMAGE_METADATA_STRUCT.size} bytes."
            )
        unpacked = IMAGE_METADATA_STRUCT.unpack(value)
        try:
            color_space = ColorSpace(unpacked[-1])
        except ValueError as exc:
            raise EnvelopeError(
                f"Unsupported image color space: {unpacked[-1]}"
            ) from exc
        return cls(*unpacked[:-1], color_space=color_space)


@dataclass(frozen=True, slots=True)
class AudioMetadata:
    model_sha256: bytes
    sample_rate: int
    original_samples: int
    frame_count: int
    padding_samples: int
    channels: int
    codebook_count: int
    bits_per_code: int
    chunk_frames: int
    bandwidth_bps: int

    def __post_init__(self) -> None:
        _validate_hash(self.model_sha256, "model_sha256")
        if self.sample_rate <= 0 or self.original_samples <= 0:
            raise EnvelopeError("Audio sample rate and sample count must be positive.")
        if self.frame_count <= 0 or self.padding_samples < 0:
            raise EnvelopeError("Audio frame count/padding is invalid.")
        if self.channels <= 0 or self.codebook_count <= 0:
            raise EnvelopeError("Audio channel and codebook counts must be positive.")
        if not 1 <= self.bits_per_code <= 16:
            raise EnvelopeError("Audio bits-per-code must be 1..16.")
        if self.chunk_frames <= 0 or self.bandwidth_bps <= 0:
            raise EnvelopeError("Audio chunk size and bandwidth must be positive.")

    def to_bytes(self) -> bytes:
        return AUDIO_METADATA_STRUCT.pack(
            self.model_sha256,
            self.sample_rate,
            self.original_samples,
            self.frame_count,
            self.padding_samples,
            self.channels,
            self.codebook_count,
            self.bits_per_code,
            self.chunk_frames,
            self.bandwidth_bps,
        )

    @classmethod
    def from_bytes(cls, value: bytes) -> AudioMetadata:
        if len(value) != AUDIO_METADATA_STRUCT.size:
            raise EnvelopeError(
                f"Audio metadata must be {AUDIO_METADATA_STRUCT.size} bytes."
            )
        return cls(*AUDIO_METADATA_STRUCT.unpack(value))


TypedMetadata = ImageMetadata | AudioMetadata


@dataclass(frozen=True, slots=True)
class Envelope:
    media_type: MediaType
    codec_profile: CodecProfile
    metadata: TypedMetadata
    payload: bytes
    flags: int = 0

    def __post_init__(self) -> None:
        if self.flags & ~SUPPORTED_FLAGS:
            raise EnvelopeError(f"Unsupported envelope flags: 0x{self.flags:04x}")
        if len(self.payload) > MAX_PAYLOAD_BYTES:
            raise EnvelopeError("Envelope payload exceeds the implementation limit.")
        if self.media_type is MediaType.IMAGE:
            if not isinstance(self.metadata, ImageMetadata):
                raise EnvelopeError("Image envelopes require ImageMetadata.")
            if self.codec_profile is not CodecProfile.BMSHJ2018_FACTORIZED_Q1:
                raise EnvelopeError("Unsupported image codec profile.")
        elif self.media_type is MediaType.AUDIO:
            if not isinstance(self.metadata, AudioMetadata):
                raise EnvelopeError("Audio envelopes require AudioMetadata.")
            if self.codec_profile is not CodecProfile.ENCODEC_24KHZ_MONO_1P5:
                raise EnvelopeError("Unsupported audio codec profile.")
            metadata = self.metadata
            packed_bits = (
                metadata.frame_count
                * metadata.codebook_count
                * metadata.bits_per_code
            )
            expected = (packed_bits + 7) // 8
            if len(self.payload) != expected:
                raise EnvelopeError(
                    f"Audio payload length {len(self.payload)} does not match "
                    f"the metadata-derived {expected} bytes."
                )
            if (
                metadata.sample_rate != 24_000
                or metadata.channels != 1
                or metadata.codebook_count != 2
                or metadata.bits_per_code != 10
                or metadata.chunk_frames != 75
                or metadata.bandwidth_bps != 1_500
            ):
                raise EnvelopeError("Audio metadata does not match profile 0x0201.")
            if metadata.frame_count % metadata.chunk_frames:
                raise EnvelopeError(
                    "Audio frames must contain complete 75-frame chunks."
                )
            expected_samples = metadata.frame_count * 320
            if metadata.original_samples + metadata.padding_samples != expected_samples:
                raise EnvelopeError("Audio sample count, frames, and padding disagree.")

    def to_bytes(self) -> bytes:
        metadata_bytes = self.metadata.to_bytes()
        header = COMMON_HEADER.pack(
            MAGIC,
            FORMAT_VERSION,
            int(self.media_type),
            int(self.codec_profile),
            self.flags,
            len(metadata_bytes),
            len(self.payload),
            hashlib.sha256(self.payload).digest(),
        )
        return header + metadata_bytes + self.payload

    @property
    def byte_length(self) -> int:
        return COMMON_HEADER.size + len(self.metadata.to_bytes()) + len(self.payload)


def _validate_hash(value: bytes, name: str) -> None:
    if not isinstance(value, bytes) or len(value) != hashlib.sha256().digest_size:
        raise EnvelopeError(f"{name} must be a 32-byte SHA-256 digest.")


def _read_exact(stream: BinaryIO, length: int, label: str) -> bytes:
    value = stream.read(length)
    if len(value) != length:
        raise EnvelopeError(
            f"Truncated {label}: expected {length} bytes, received {len(value)}."
        )
    return value


def read_envelope(stream: BinaryIO, *, require_eof: bool = True) -> Envelope:
    header_bytes = _read_exact(stream, COMMON_HEADER.size, "common header")
    (
        magic,
        version,
        media_value,
        profile_value,
        flags,
        metadata_length,
        payload_length,
        expected_payload_hash,
    ) = COMMON_HEADER.unpack(header_bytes)

    if magic != MAGIC:
        raise EnvelopeError(f"Invalid LightWeave magic: {magic!r}")
    if version != FORMAT_VERSION:
        raise EnvelopeError(f"Unsupported LightWeave format version: {version}")
    if flags & ~SUPPORTED_FLAGS:
        raise EnvelopeError(f"Unsupported envelope flags: 0x{flags:04x}")
    if metadata_length > MAX_METADATA_BYTES:
        raise EnvelopeError("Envelope metadata exceeds the implementation limit.")
    if payload_length > MAX_PAYLOAD_BYTES:
        raise EnvelopeError("Envelope payload exceeds the implementation limit.")

    try:
        media_type = MediaType(media_value)
    except ValueError as exc:
        raise EnvelopeError(f"Unsupported media type: {media_value}") from exc
    try:
        codec_profile = CodecProfile(profile_value)
    except ValueError as exc:
        raise EnvelopeError(
            f"Unsupported codec profile: 0x{profile_value:04x}"
        ) from exc

    metadata_bytes = _read_exact(stream, metadata_length, "typed metadata")
    payload = _read_exact(stream, payload_length, "payload")
    if require_eof and stream.read(1):
        raise EnvelopeError("Unexpected trailing bytes after the LightWeave payload.")
    actual_payload_hash = hashlib.sha256(payload).digest()
    if actual_payload_hash != expected_payload_hash:
        raise IntegrityError("LightWeave payload SHA-256 validation failed.")

    if media_type is MediaType.IMAGE:
        metadata: TypedMetadata = ImageMetadata.from_bytes(metadata_bytes)
    else:
        metadata = AudioMetadata.from_bytes(metadata_bytes)

    return Envelope(media_type, codec_profile, metadata, payload, flags)


def parse_envelope(value: bytes) -> Envelope:
    return read_envelope(io.BytesIO(value))


def envelope_summary(envelope: Envelope) -> dict[str, object]:
    common: dict[str, object] = {
        "format_version": FORMAT_VERSION,
        "media_type": envelope.media_type.name.lower(),
        "codec_profile": f"0x{int(envelope.codec_profile):04x}",
        "flags": envelope.flags,
        "envelope_bytes": envelope.byte_length,
        "payload_bytes": len(envelope.payload),
        "payload_sha256": hashlib.sha256(envelope.payload).hexdigest(),
        "model_sha256": envelope.metadata.model_sha256.hex(),
    }
    if isinstance(envelope.metadata, ImageMetadata):
        common["image"] = {
            "original_size": [
                envelope.metadata.original_width,
                envelope.metadata.original_height,
            ],
            "content_size": [
                envelope.metadata.content_width,
                envelope.metadata.content_height,
            ],
            "padding": [
                envelope.metadata.pad_left,
                envelope.metadata.pad_top,
                envelope.metadata.pad_right,
                envelope.metadata.pad_bottom,
            ],
            "latent_shape": [
                1,
                envelope.metadata.latent_channels,
                envelope.metadata.latent_height,
                envelope.metadata.latent_width,
            ],
            "quality": envelope.metadata.quality,
            "color_space": envelope.metadata.color_space.name,
        }
    else:
        common["audio"] = {
            "sample_rate": envelope.metadata.sample_rate,
            "original_samples": envelope.metadata.original_samples,
            "frame_count": envelope.metadata.frame_count,
            "padding_samples": envelope.metadata.padding_samples,
            "channels": envelope.metadata.channels,
            "codebook_count": envelope.metadata.codebook_count,
            "bits_per_code": envelope.metadata.bits_per_code,
            "chunk_frames": envelope.metadata.chunk_frames,
            "bandwidth_bps": envelope.metadata.bandwidth_bps,
        }
    return common
