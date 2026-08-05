from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

from lightweave.audio import LoadedAudio
from lightweave.raw import (
    RAW_AUDIO_CHUNK_BYTES,
    RAW_IMAGE_PRESET,
    decode_raw_audio,
    decode_raw_image,
    encode_raw_audio,
    encode_raw_image,
    pack_raw_audio_chunks,
    parse_raw_audio_preset,
    parse_raw_image_preset,
    raw_audio_preset,
    unpack_raw_audio_chunks,
)
from lightweave.transport import MemoryRawPipe, RawByteSink, RawByteSource


def test_raw_preset_parsing_is_strict() -> None:
    assert parse_raw_image_preset("I64-Q1") == RAW_IMAGE_PRESET
    assert raw_audio_preset(48_000) == "A1-E15-S48000"
    assert parse_raw_audio_preset("A1-E15-S48000") == 48_000
    with pytest.raises(ValueError, match="Unsupported raw image preset"):
        parse_raw_image_preset("I256-Q1")
    with pytest.raises(ValueError, match="Malformed raw audio preset"):
        parse_raw_audio_preset("A1-E15-S0")


def test_raw_audio_chunks_are_independent_188_byte_messages() -> None:
    values = torch.arange(300, dtype=torch.int64).reshape(1, 2, 150) % 1024
    payload = pack_raw_audio_chunks(values)
    assert len(payload) == 2 * RAW_AUDIO_CHUNK_BYTES
    assert payload[187] & 0xF0 == 0
    assert payload[375] & 0xF0 == 0
    assert torch.equal(unpack_raw_audio_chunks(payload), values)


def test_raw_audio_rejects_bad_lengths_and_padding_bits() -> None:
    with pytest.raises(ValueError, match="divisible by 188"):
        unpack_raw_audio_chunks(bytes(187))
    invalid = bytearray(188)
    invalid[-1] = 0x10
    with pytest.raises(ValueError, match="non-zero padding bits"):
        unpack_raw_audio_chunks(bytes(invalid))


def test_raw_audio_sample_count_must_match_chunk_count() -> None:
    with pytest.raises(ValueError, match="impossible"):
        decode_raw_audio(
            bytes(2 * RAW_AUDIO_CHUNK_BYTES),
            preset_code="A1-E15-S24000",
            backend="cpu",
        )


def test_arbitrary_audio_duration_restores_exact_sample_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Quantizer:
        def decode(self, codes: torch.Tensor) -> torch.Tensor:
            assert tuple(codes.shape) == (2, 1, 150)
            return torch.zeros((1, 8, 150), dtype=torch.float32)

    class Model:
        quantizer = Quantizer()

        def encode(self, waveform: torch.Tensor) -> list[tuple[torch.Tensor, None]]:
            assert tuple(waveform.shape) == (1, 1, 48_000)
            return [(torch.zeros((1, 2, 150), dtype=torch.int64), None)]

        def decoder(self, embedding: torch.Tensor) -> torch.Tensor:
            assert tuple(embedding.shape) == (1, 8, 150)
            return torch.zeros((1, 1, 48_000), dtype=torch.float32)

    model = Model()
    monkeypatch.setattr(
        "lightweave.raw.load_wav",
        lambda path: LoadedAudio(torch.zeros((1, 1, 36_000)), 24_000, 36_000),
    )
    monkeypatch.setattr(
        "lightweave.raw.load_audio_model",
        lambda weights_path=None: (model, Path("weights"), bytes(32)),
    )
    encoded = encode_raw_audio(Path("input.wav"))
    assert encoded.preset_code == "A1-E15-S36000"
    assert encoded.chunk_count == 2
    assert len(encoded.payload) == 376
    decoded = decode_raw_audio(
        encoded.payload, preset_code=encoded.preset_code, backend="cpu"
    )
    assert tuple(decoded.waveform.shape) == (1, 1, 36_000)


def test_raw_image_selects_highest_detail_that_fits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.png"
    Image.fromarray(np.full((30, 80, 3), 120, dtype=np.uint8)).save(source)
    sizes = iter((140, 120))
    monkeypatch.setattr(
        "lightweave.raw.load_image_model",
        lambda weights_path=None: (object(), Path("weights"), bytes(32)),
    )
    monkeypatch.setattr(
        "lightweave.raw._compress_raw_image",
        lambda model, image: bytes(next(sizes)),
    )
    encoded = encode_raw_image(source)
    assert encoded.effective_detail == 56
    assert encoded.fallback == "none"
    assert len(encoded.payload) == 120
    assert encoded.reference.size == (64, 64)


def test_raw_image_encoder_accepts_binary_streams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = io.BytesIO()
    Image.new("RGB", (12, 8), (1, 2, 3)).save(stream, format="PNG")
    stream.seek(0)
    monkeypatch.setattr(
        "lightweave.raw.load_image_model",
        lambda weights_path=None: (object(), Path("weights"), bytes(32)),
    )
    monkeypatch.setattr(
        "lightweave.raw._compress_raw_image",
        lambda model, image: bytes(64),
    )
    encoded = encode_raw_image(stream)
    assert len(encoded.payload) == 64
    assert encoded.effective_detail == 64


def test_raw_image_uses_mean_color_before_black_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.png"
    Image.new("RGB", (16, 16), (20, 40, 60)).save(source)
    sizes = iter([129] * 8 + [64])
    monkeypatch.setattr(
        "lightweave.raw.load_image_model",
        lambda weights_path=None: (object(), Path("weights"), bytes(32)),
    )
    monkeypatch.setattr(
        "lightweave.raw._compress_raw_image",
        lambda model, image: bytes(next(sizes)),
    )
    encoded = encode_raw_image(source)
    assert encoded.effective_detail == 0
    assert encoded.fallback == "mean-color"
    assert encoded.reference.getpixel((0, 0)) == (20, 40, 60)


def test_raw_image_uses_deterministic_black_as_final_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.png"
    Image.new("RGB", (16, 16), (20, 40, 60)).save(source)
    sizes = iter([129] * 9 + [48])
    monkeypatch.setattr(
        "lightweave.raw.load_image_model",
        lambda weights_path=None: (object(), Path("weights"), bytes(32)),
    )
    monkeypatch.setattr(
        "lightweave.raw._compress_raw_image",
        lambda model, image: bytes(next(sizes)),
    )
    encoded = encode_raw_image(source)
    assert encoded.fallback == "black"
    assert encoded.reference.getpixel((0, 0)) == (0, 0, 0)
    assert len(encoded.payload) == 48


def test_raw_image_fails_if_black_fallback_breaks_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.png"
    Image.new("RGB", (16, 16)).save(source)
    monkeypatch.setattr(
        "lightweave.raw.load_image_model",
        lambda weights_path=None: (object(), Path("weights"), bytes(32)),
    )
    monkeypatch.setattr(
        "lightweave.raw._compress_raw_image",
        lambda model, image: bytes(129),
    )
    with pytest.raises(RuntimeError, match="black fallback"):
        encode_raw_image(source)


def test_raw_image_rejects_payload_above_wire_limit() -> None:
    with pytest.raises(ValueError, match="maximum is 128"):
        decode_raw_image(
            bytes(129), preset_code=RAW_IMAGE_PRESET, backend="cpu"
        )


def test_memory_raw_pipe_implements_adapter_contracts() -> None:
    pipe = MemoryRawPipe()
    assert isinstance(pipe, RawByteSink)
    assert isinstance(pipe, RawByteSource)
    receipt = pipe.send(b"optical bytes")
    assert receipt.bytes_sent == 13
    assert receipt.adapter == "memory-loopback"
    assert pipe.receive() == b"optical bytes"
