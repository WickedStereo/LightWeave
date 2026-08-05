from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
import torch

from lightweave.audio import pack_codes, unpack_codes, write_wav_atomic
from lightweave.envelope import (
    AudioMetadata,
    CodecProfile,
    Envelope,
    MediaType,
    parse_envelope,
)
from lightweave.errors import EnvelopeError


def audio_metadata() -> AudioMetadata:
    return AudioMetadata(
        model_sha256=hashlib.sha256(b"encodec").digest(),
        sample_rate=24_000,
        original_samples=24_000,
        frame_count=75,
        padding_samples=0,
        channels=1,
        codebook_count=2,
        bits_per_code=10,
        chunk_frames=75,
        bandwidth_bps=1_500,
    )


def test_ten_bit_code_packing_round_trip() -> None:
    values = torch.arange(150, dtype=torch.int64).reshape(1, 2, 75) % 1024
    packed = pack_codes(values)
    assert len(packed) == 188
    assert torch.equal(unpack_codes(packed, 75), values)


def test_audio_envelope_round_trip() -> None:
    payload = bytes(188)
    envelope = Envelope(
        MediaType.AUDIO,
        CodecProfile.ENCODEC_24KHZ_MONO_1P5,
        audio_metadata(),
        payload,
    )
    assert parse_envelope(envelope.to_bytes()) == envelope


def test_audio_payload_length_must_match_metadata() -> None:
    with pytest.raises(EnvelopeError, match="payload length"):
        Envelope(
            MediaType.AUDIO,
            CodecProfile.ENCODEC_24KHZ_MONO_1P5,
            audio_metadata(),
            b"too short",
        )


def test_atomic_wav_writer_preserves_sample_count(tmp_path: Path) -> None:
    output = tmp_path / "output.wav"
    waveform = torch.from_numpy(np.linspace(-0.5, 0.5, 2400, dtype=np.float32))
    write_wav_atomic(waveform, output)
    import wave

    with wave.open(str(output), "rb") as stream:
        assert stream.getframerate() == 24_000
        assert stream.getnchannels() == 1
        assert stream.getnframes() == 2400
