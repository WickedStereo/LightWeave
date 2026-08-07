from __future__ import annotations

import pytest

from lightweave.text import MAX_TEXT_BYTES, decode_text, encode_text


def test_text_payload_is_exact_printable_ascii() -> None:
    message = "Hello, LightWeave! 123"
    payload = encode_text(message)
    assert payload == b"Hello, LightWeave! 123"
    assert decode_text(payload) == message


@pytest.mark.parametrize(
    "message", ["", "line\nbreak", "caf\N{LATIN SMALL LETTER E WITH ACUTE}", "x" * 101]
)
def test_text_encoder_fails_closed(message: str) -> None:
    with pytest.raises(ValueError):
        encode_text(message)


@pytest.mark.parametrize("payload", [b"", b"line\nbreak", bytes([0x7F]), b"x" * 101])
def test_text_decoder_fails_closed(payload: bytes) -> None:
    with pytest.raises(ValueError):
        decode_text(payload)


def test_text_limit_is_one_hundred_bytes() -> None:
    assert MAX_TEXT_BYTES == 100
    assert len(encode_text("x" * MAX_TEXT_BYTES)) == MAX_TEXT_BYTES
