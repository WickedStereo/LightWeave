from __future__ import annotations

import hashlib
import io

import pytest

from lightweave.envelope import (
    COMMON_HEADER,
    CodecProfile,
    ColorSpace,
    Envelope,
    ImageMetadata,
    MediaType,
    parse_envelope,
    read_envelope,
)
from lightweave.errors import EnvelopeError, IntegrityError


def image_metadata() -> ImageMetadata:
    return ImageMetadata(
        model_sha256=hashlib.sha256(b"model").digest(),
        original_width=640,
        original_height=360,
        content_width=256,
        content_height=144,
        pad_left=0,
        pad_top=56,
        pad_right=0,
        pad_bottom=56,
        latent_channels=192,
        latent_height=16,
        latent_width=16,
        quality=1,
        color_space=ColorSpace.RGB,
    )


def test_image_envelope_round_trip() -> None:
    original = Envelope(
        MediaType.IMAGE,
        CodecProfile.BMSHJ2018_FACTORIZED_Q1,
        image_metadata(),
        b"entropy bytes",
    )
    decoded = parse_envelope(original.to_bytes())
    assert decoded == original
    assert decoded.byte_length == len(original.to_bytes())


def test_payload_corruption_is_rejected() -> None:
    value = bytearray(
        Envelope(
            MediaType.IMAGE,
            CodecProfile.BMSHJ2018_FACTORIZED_Q1,
            image_metadata(),
            b"entropy bytes",
        ).to_bytes()
    )
    value[-1] ^= 0xFF
    with pytest.raises(IntegrityError, match="SHA-256"):
        parse_envelope(bytes(value))


@pytest.mark.parametrize("removed", [1, 5, COMMON_HEADER.size])
def test_truncation_is_rejected(removed: int) -> None:
    value = Envelope(
        MediaType.IMAGE,
        CodecProfile.BMSHJ2018_FACTORIZED_Q1,
        image_metadata(),
        b"entropy bytes",
    ).to_bytes()
    with pytest.raises(EnvelopeError, match="Truncated"):
        parse_envelope(value[:-removed])


def test_trailing_bytes_are_rejected() -> None:
    value = Envelope(
        MediaType.IMAGE,
        CodecProfile.BMSHJ2018_FACTORIZED_Q1,
        image_metadata(),
        b"entropy bytes",
    ).to_bytes()
    with pytest.raises(EnvelopeError, match="trailing"):
        parse_envelope(value + b"unexpected")


def test_stream_can_leave_next_envelope_unread_when_requested() -> None:
    envelope = Envelope(
        MediaType.IMAGE,
        CodecProfile.BMSHJ2018_FACTORIZED_Q1,
        image_metadata(),
        b"entropy bytes",
    )
    stream = io.BytesIO(envelope.to_bytes() + b"next")
    decoded = read_envelope(stream, require_eof=False)
    assert decoded == envelope
    assert stream.read() == b"next"


def test_inconsistent_padding_is_rejected() -> None:
    with pytest.raises(EnvelopeError, match="Horizontal"):
        ImageMetadata(
            model_sha256=hashlib.sha256(b"model").digest(),
            original_width=100,
            original_height=100,
            content_width=200,
            content_height=256,
            pad_left=20,
            pad_top=0,
            pad_right=20,
            pad_bottom=0,
            latent_channels=192,
            latent_height=16,
            latent_width=16,
        )


def test_unsupported_version_is_rejected() -> None:
    envelope = Envelope(
        MediaType.IMAGE,
        CodecProfile.BMSHJ2018_FACTORIZED_Q1,
        image_metadata(),
        b"entropy bytes",
    )
    value = bytearray(envelope.to_bytes())
    value[4] = 2
    with pytest.raises(EnvelopeError, match="format version"):
        parse_envelope(bytes(value))


def test_unsupported_codec_profile_is_rejected() -> None:
    envelope = Envelope(
        MediaType.IMAGE,
        CodecProfile.BMSHJ2018_FACTORIZED_Q1,
        image_metadata(),
        b"entropy bytes",
    )
    value = bytearray(envelope.to_bytes())
    value[6:8] = (0x9999).to_bytes(2, "little")
    with pytest.raises(EnvelopeError, match="codec profile"):
        parse_envelope(bytes(value))
