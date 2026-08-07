"""Deterministic no-model text payload contract for LightWeave."""

from __future__ import annotations

TEXT_PRESET_CODE = "T1-ASCII-B100"
MAX_TEXT_BYTES = 100


def encode_text(text: str) -> bytes:
    """Encode one printable-ASCII message without compression or AI."""

    if not isinstance(text, str):
        raise ValueError("Text must be a string.")
    if not text:
        raise ValueError("Text is empty.")
    try:
        payload = text.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("Text must contain printable ASCII characters only.") from exc
    if len(payload) > MAX_TEXT_BYTES:
        raise ValueError(f"Text exceeds the {MAX_TEXT_BYTES}-byte limit.")
    if any(value < 32 or value > 126 for value in payload):
        raise ValueError("Text must contain printable ASCII characters only.")
    return payload


def decode_text(payload: bytes) -> str:
    """Validate and decode one production text payload."""

    value = bytes(payload)
    if not value:
        raise ValueError("Text payload is empty.")
    if len(value) > MAX_TEXT_BYTES:
        raise ValueError(f"Text payload exceeds the {MAX_TEXT_BYTES}-byte limit.")
    if any(byte < 32 or byte > 126 for byte in value):
        raise ValueError("Text payload contains non-printable ASCII bytes.")
    return value.decode("ascii")
