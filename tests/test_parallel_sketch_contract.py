from __future__ import annotations

from pathlib import Path

import pytest

from lightweave.optical_frame import build_frame, parse_frame

ROOT = Path(__file__).resolve().parents[1]
LANES = 3


def _parallel_slots(frame: bytes) -> list[tuple[int, int, int]]:
    padded = frame + bytes((-len(frame)) % LANES)
    return [
        tuple(padded[offset : offset + LANES])  # type: ignore[misc]
        for offset in range(0, len(padded), LANES)
    ]


def _reassemble(slots: list[tuple[int, int, int]], frame_bytes: int) -> bytes:
    return bytes(value for slot in slots for value in slot)[:frame_bytes]


@pytest.mark.parametrize(
    ("payload", "preset"),
    [
        (b"3-LANE", "T1-ASCII-B100"),
        (bytes(range(128)), "I64-Q1-B128"),
        (bytes(index % 256 for index in range(768)), "I128-Q1-B768"),
        (bytes(index % 256 for index in range(2048)), "I256-Q1-B2048"),
        (bytes(188), "A1-E15-S24000"),
        (bytes(940), "A1-E15-S120000"),
    ],
)
def test_three_lane_byte_striping_preserves_complete_lwf1_frame(
    payload: bytes, preset: str
) -> None:
    frame = build_frame(payload, preset)
    slots = _parallel_slots(frame)
    restored_frame = _reassemble(slots, len(frame))
    parsed, restored_payload, _ = parse_frame(restored_frame)
    assert restored_frame == frame
    assert restored_payload == payload
    assert parsed.preset_code == preset


def test_short_text_slot_assignment_and_duration() -> None:
    frame = build_frame(b"3-LANE", "T1-ASCII-B100")
    slots = _parallel_slots(frame)
    assert slots[0] == (frame[0], frame[1], frame[2])
    assert slots[1] == (frame[3], frame[4], frame[5])
    assert len(frame) == 18
    assert len(slots) == 6
    assert (2 + 8 * len(slots)) * 0.025 == pytest.approx(1.25)
    assert (2 + 8 * len(frame)) * 0.025 == pytest.approx(3.65)


def test_partial_final_slot_padding_is_not_reassembled() -> None:
    frame = build_frame(b"AB", "T1-ASCII-B100")
    slots = _parallel_slots(frame)
    assert len(frame) == 14
    assert slots[-1][2] == 0
    assert _reassemble(slots, len(frame)) == frame


def test_sketches_use_requested_pins_and_compatible_bridge_contract() -> None:
    transmitter = (
        ROOT / "uno_q/parallel_transmitter_app/sketch/sketch.ino"
    ).read_text(encoding="utf-8")
    receiver = (
        ROOT / "uno_q/parallel_receiver_app/sketch/sketch.ino"
    ).read_text(encoding="utf-8")

    assert "{5, 7, 9}" in transmitter
    assert "{A0, A2, A5}" in receiver
    assert "wireIndex = slot * LightWeaveParallel::kLaneCount + lane" in transmitter
    assert "consumeWireByte(value);" in receiver

    for method in (
        "prepare_transmission",
        "store_image_byte",
        "transmit_payload",
        "get_loaded_byte_count",
        "set_lane_test_mask",
    ):
        assert f'Bridge.provide("{method}"' in transmitter
    for method in (
        "start_listen",
        "cancel_receive",
        "get_received_byte_count",
        "get_received_chunk",
        "get_frame_header",
        "get_frame_profile_id",
        "get_media_parameter",
        "get_received_crc",
        "get_computed_crc",
        "get_stop_bit_valid",
        "get_receiver_error_code",
        "get_sensor_reading",
        "get_sensor_threshold",
        "get_lane_high_mask",
    ):
        assert f'Bridge.provide("{method}"' in receiver
