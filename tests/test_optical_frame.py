from __future__ import annotations

import pytest

from lightweave import optical_frame as frame


def test_canonical_image_vector() -> None:
    payload = bytes.fromhex("00ffaa55")
    wire = frame.build_frame(payload, "I64-Q1-B128")
    assert wire[:10].hex() == "4c570101040000000000"
    assert wire[-2:].hex() == "f853"
    parsed, restored, crc = frame.parse_frame(wire)
    assert parsed.preset_code == "I64-Q1-B128"
    assert restored == payload
    assert crc == 0x53F8


def test_canonical_audio_vector() -> None:
    payload = bytes(188)
    wire = frame.build_frame(payload, "A1-E15-S24000")
    assert wire[:10].hex() == "4c570110bc00c05d0000"
    assert wire[-2:].hex() == "2163"
    parsed, restored, crc = frame.parse_frame(wire)
    assert parsed.preset_code == "A1-E15-S24000"
    assert restored == payload
    assert crc == 0x6321


@pytest.mark.parametrize(
    ("preset", "payload_bytes", "profile_id"),
    [
        ("I64-Q1-B128", 128, 0x01),
        ("I128-Q1-B768", 768, 0x02),
        ("I256-Q1-B2048", 2048, 0x03),
        ("A1-E15-S1", 188, 0x10),
        ("A1-E15-S120000", 940, 0x10),
    ],
)
def test_profiles_and_endianness(
    preset: str, payload_bytes: int, profile_id: int
) -> None:
    header = frame.build_header(preset, payload_bytes)
    assert header[3] == profile_id
    assert int.from_bytes(header[4:6], "little") == payload_bytes


def test_frame_rejects_corruption_and_invalid_contracts() -> None:
    wire = bytearray(frame.build_frame(b"abc", "I64-Q1-B128"))
    wire[10] ^= 1
    with pytest.raises(frame.FrameError, match="CRC"):
        frame.parse_frame(bytes(wire))
    with pytest.raises(frame.FrameError, match="parameter"):
        frame.parse_header(bytes.fromhex("4c570101040001000000"))
    with pytest.raises(frame.FrameError, match="divisible"):
        frame.build_header("A1-E15-S24000", 189)
    with pytest.raises(frame.FrameError, match="padding"):
        frame.build_frame(bytes(187) + b"\xf0", "A1-E15-S24000")


def test_duration_includes_wire_only_overhead() -> None:
    assert frame.transmission_seconds(80) == pytest.approx(18.45)
    assert frame.transmission_seconds(188) == pytest.approx(40.05)
    assert frame.transmission_seconds(940) == pytest.approx(190.45)
    assert frame.transmission_seconds(4, "raw-v0") == pytest.approx(0.85)
