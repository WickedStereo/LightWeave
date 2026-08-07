from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path

import pytest

from lightweave.optical_frame import build_frame, build_header, crc16_ccitt_false

APP_ROOT = Path(__file__).resolve().parents[1] / "uno_q" / "optical_receiver_app"
APP_PYTHON = APP_ROOT / "python"
sys.path.insert(0, str(APP_PYTHON))

import lightweave_optical_receiver as optical  # noqa: E402


class FakeBridge:
    def __init__(
        self,
        payload: bytes,
        preset: str = "I256-Q1-B2048",
        *,
        reported_count: int | None = None,
        received_crc: int | None = None,
        error_code: str = "none",
        stop_bit_valid: bool = True,
    ) -> None:
        self.payload = payload
        self.header = build_header(preset, len(payload))
        self.reported_count = reported_count
        self.crc = crc16_ccitt_false(self.header + payload)
        self.received_crc = self.crc if received_crc is None else received_crc
        self.error_code = error_code
        self.stop_bit_valid = stop_bit_valid
        self.chunks: list[tuple[int, int]] = []

    def call(self, method: str, *args: object) -> object:
        if method == "get_receiver_error_code":
            return self.error_code
        if method == "get_frame_header":
            return self.header.hex().upper()
        if method == "get_received_byte_count":
            return (
                len(self.payload)
                if self.reported_count is None
                else self.reported_count
            )
        if method == "get_received_chunk":
            offset, count = (int(value) for value in args)
            self.chunks.append((offset, count))
            return self.payload[offset : offset + count].hex().upper()
        if method == "get_received_crc":
            return self.received_crc
        if method == "get_computed_crc":
            return self.crc
        if method == "get_stop_bit_valid":
            return self.stop_bit_valid
        raise AssertionError(method)


def test_listen_request_needs_no_manual_media_settings() -> None:
    request_id = str(uuid.uuid4())
    request = optical.parse_listen_request(
        {
            "schema_version": 2,
            "request_id": request_id,
            "action": "listen-lwf1",
        },
        source="test",
    )
    assert request == optical.ReceiveRequest(request_id, "test")
    with pytest.raises(optical.ReceiverError, match="schema"):
        optical.parse_listen_request(
            {"schema_version": 1, "request_id": request_id}, source="test"
        )


def test_collect_preserves_every_byte_and_validates_frame() -> None:
    payload = bytes(range(256))
    bridge = FakeBridge(payload)
    received = optical.collect_received_frame(bridge)
    assert received.payload == payload
    assert received.header.preset_code == "I256-Q1-B2048"
    assert received.received_crc == received.computed_crc
    assert bridge.chunks == [(offset, 32) for offset in range(0, 256, 32)]


def test_collect_accepts_canonical_audio_frame() -> None:
    payload = bytes(188)
    bridge = FakeBridge(payload, "A1-E15-S24000")
    received = optical.collect_received_frame(bridge)
    assert received.header.profile.media_type == "audio"
    assert received.header.media_parameter == 24_000
    assert received.received_crc == 0x6321


def test_collect_accepts_exact_printable_ascii_text_frame() -> None:
    payload = b"Hello LightWeave"
    received = optical.collect_received_frame(FakeBridge(payload, "T1-ASCII-B100"))
    assert received.header.profile.media_type == "text"
    assert received.header.profile.profile_id == 0x20
    assert received.payload == payload


@pytest.mark.parametrize(
    ("bridge", "message"),
    [
        (FakeBridge(b"abcd", reported_count=3), "reports 3 bytes"),
        (FakeBridge(b"abcd", received_crc=0), "CRC mismatch"),
        (FakeBridge(b"abcd", stop_bit_valid=False), "stop bit"),
        (FakeBridge(b"abcd", error_code="bad-magic"), "bad-magic"),
    ],
)
def test_collect_rejects_invalid_stm32_evidence(
    bridge: FakeBridge, message: str
) -> None:
    with pytest.raises(optical.ReceiverError, match=message):
        optical.collect_received_frame(bridge)


@pytest.mark.parametrize(
    ("preset", "extension", "media_type"),
    [
        ("I64-Q1-B128", "png", "image"),
        ("A1-E15-S24000", "wav", "audio"),
        ("T1-ASCII-B100", "txt", "text"),
    ],
)
def test_store_claims_listen_and_records_media_atomically(
    tmp_path: Path, preset: str, extension: str, media_type: str
) -> None:
    store = optical.ReceiverStore(tmp_path)
    request_id = str(uuid.uuid4())
    descriptor = {
        "schema_version": 2,
        "request_id": request_id,
        "action": "listen-lwf1",
    }
    (store.inbox / f"{request_id}.json").write_text(
        json.dumps(descriptor), encoding="utf-8"
    )
    request = store.claim_next()
    assert request == optical.ReceiveRequest(request_id, "adb")
    if media_type == "audio":
        payload = bytes(188)
    elif media_type == "text":
        payload = b"Hello LightWeave"
    else:
        payload = b"\x00\xff\xaa\x55"
    bridge = FakeBridge(payload, preset)
    frame = optical.collect_received_frame(bridge)
    media = b"media-fixture"
    metrics = {
        "backend": "ncnn-vulkan",
        "device": "Turnip Adreno 702",
        "strict_no_fallback": True,
    }
    result = store.write_result(
        request,
        frame,
        media,
        output_extension=extension,
        metrics=metrics,
    )
    assert result["payload_sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["media_type"] == media_type
    assert result["crc_valid"] is True
    assert (store.results / f"{request_id}.bin").read_bytes() == payload
    assert (store.results / f"{request_id}.{extension}").read_bytes() == media
    assert not list(store.results.glob("*.partial"))


def test_canonical_wire_vector_extracts_unchanged_payload() -> None:
    wire = build_frame(bytes.fromhex("00ffaa55"), "I64-Q1-B128")
    assert wire[10:-2].hex() == "00ffaa55"
    assert wire[-2:].hex() == "f853"


def test_tracked_app_preserves_hardware_and_accelerator_contracts() -> None:
    sketch = (APP_ROOT / "sketch" / "sketch.ino").read_text(encoding="utf-8")
    main = (APP_ROOT / "python" / "main.py").read_text(encoding="utf-8")
    page = (APP_ROOT / "assets" / "index.html").read_text(encoding="utf-8")
    assert "bitDurationUs = 25000UL" in sketch
    assert "sensorPin = A0" in sketch
    assert "sensorThreshold = 800" in sketch
    assert 'Bridge.provide("start_listen"' in sketch
    assert 'Bridge.provide("cancel_receive"' in sketch
    assert "from lightweave_uno import decode_audio_payload, decode_payload" in main
    assert "decode_payload(frame.payload, frame.header.preset_code)" in main
    assert "decode_audio_payload(frame.payload, frame.header.preset_code)" in main
    assert 'frame.payload.decode("ascii")' in main
    assert 'accelerator_required": False' in main
    assert 'metrics["hardware_usage"] = hardware_usage(frame, metrics)' in main
    assert '"decoded_optical_bits": optical_bits' in main
    assert '"Adreno 702 GPU"' in main
    assert 'id="text-content"' in page
    assert 'id="theme-toggle"' in page
    assert "Download TXT" in page
    assert "Listen for transfer" in page
    assert "http://" not in page
    assert "https://" not in page
