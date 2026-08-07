from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

PHONE_MODULE = (
    Path(__file__).resolve().parents[1]
    / "uno_q"
    / "optical_receiver_app"
    / "python"
)
sys.path.insert(0, str(PHONE_MODULE))

from phone_usb import (  # noqa: E402
    CONTROL,
    HEADER,
    PhoneUsbError,
    PhoneUsbOutbox,
    PhoneUsbUnavailable,
    RouterMonitorTransport,
    build_control_frame,
    build_phone_frame,
    parse_control_frame,
    parse_phone_frame,
)


class FakeBridge:
    def __init__(self) -> None:
        self.connected = True
        self.reads: list[object] = []
        self.writes: list[bytes] = []

    def call(self, method: str, *params, timeout: int = 10):
        del timeout
        if method == "mon/connected":
            return self.connected
        if method == "mon/read":
            return self.reads.pop(0) if self.reads else b""
        if method == "mon/write":
            data = bytes(params[0])
            self.writes.append(data)
            return len(data)
        raise AssertionError(method)


@pytest.mark.parametrize(
    "media_type,payload",
    [
        ("text", b"Hello Galaxy"),
        ("image", b"\x89PNG\r\n\x1a\nfixture"),
        ("audio", b"RIFFfixtureWAVE"),
        ("status", b'{"status":"idle"}'),
    ],
)
def test_phone_frame_round_trip(media_type: str, payload: bytes) -> None:
    metadata = {"preset_code": "fixture", "hardware_usage": {"cpu": True}}
    frame = build_phone_frame(media_type, metadata, payload)
    parsed = parse_phone_frame(frame)
    assert parsed.media_type == media_type
    assert parsed.metadata == metadata
    assert parsed.payload == payload
    assert len(frame) == HEADER.size + len(payload) + len(
        json.dumps(metadata, separators=(",", ":"), sort_keys=True).encode()
    )


def test_phone_frame_crc_and_contract_fail_closed() -> None:
    frame = bytearray(build_phone_frame("text", {"value": 1}, b"hello"))
    frame[-1] ^= 0x01
    with pytest.raises(PhoneUsbError, match="CRC-32"):
        parse_phone_frame(bytes(frame))
    with pytest.raises(PhoneUsbError, match="Unsupported"):
        build_phone_frame("video", {}, b"value")
    with pytest.raises(PhoneUsbError, match="empty"):
        build_phone_frame("text", {}, b"")


def test_phone_text_frame_matches_android_canonical_vector() -> None:
    assert build_phone_frame(
        "text", {"preset_code": "T1-ASCII-B100"}, b"OK"
    ).hex() == (
        "4c575258020100001f000000020000000f47257a"
        "7b227072657365745f636f6465223a2254312d41534349492d42313030227d4f4b"
    )


@pytest.mark.parametrize("command", ["listen", "cancel", "status"])
def test_phone_control_frame_round_trip(command: str) -> None:
    frame = build_control_frame(command)
    assert len(frame) == CONTROL.size == 12
    assert parse_control_frame(frame) == command


def test_phone_control_crc_and_contract_fail_closed() -> None:
    frame = bytearray(build_control_frame("listen"))
    frame[-1] ^= 0x01
    with pytest.raises(PhoneUsbError, match="CRC-32"):
        parse_control_frame(bytes(frame))
    with pytest.raises(PhoneUsbError, match="Unsupported"):
        build_control_frame("restart")
    with pytest.raises(PhoneUsbError, match="exactly 12"):
        parse_control_frame(b"LWCT")


def test_outbox_is_atomic_and_records_delivery(tmp_path: Path) -> None:
    request_id = str(uuid.uuid4())
    results = tmp_path / "data" / "results"
    results.mkdir(parents=True)
    (results / f"{request_id}.json").write_text(
        json.dumps({"request_id": request_id}), encoding="utf-8"
    )
    bridge = FakeBridge()
    outbox = PhoneUsbOutbox(
        tmp_path,
        transport=RouterMonitorTransport(bridge),
    )
    queued = outbox.enqueue(
        request_id,
        "audio",
        {"preset_code": "A1-E15-S24000"},
        b"RIFFfixtureWAVE",
    )
    assert queued["status"] == "queued"
    assert not list(outbox.outbox.glob("*.partial"))

    receipt = outbox.deliver_once()
    assert receipt is not None
    assert receipt["status"] == "sent"
    assert receipt["media_type"] == "audio"
    assert not list(outbox.outbox.glob("*.lwr2"))
    assert parse_phone_frame(bridge.writes[0]).payload == b"RIFFfixtureWAVE"
    stored = json.loads((results / f"{request_id}.json").read_text())
    assert stored["phone_usb"]["status"] == "sent"


def test_outbox_sends_ephemeral_status(tmp_path: Path) -> None:
    bridge = FakeBridge()
    receipt = PhoneUsbOutbox(
        tmp_path,
        transport=RouterMonitorTransport(bridge),
    ).send_status({"status": "idle"})
    assert receipt["status"] == "sent"
    parsed = parse_phone_frame(bridge.writes[0])
    assert parsed.media_type == "status"
    assert json.loads(parsed.payload) == {"status": "idle"}


def test_router_monitor_transport_reads_bytes_and_integer_lists() -> None:
    bridge = FakeBridge()
    bridge.reads.extend([b"LW", [67, 84]])
    transport = RouterMonitorTransport(bridge)
    assert transport.read() == b"LW"
    assert transport.read() == b"CT"
    assert transport.status()["router_connected"] is True


def test_router_monitor_transport_fails_closed() -> None:
    bridge = FakeBridge()
    bridge.connected = False
    transport = RouterMonitorTransport(bridge)
    with pytest.raises(PhoneUsbUnavailable, match="not connected"):
        transport.read()
    with pytest.raises(PhoneUsbUnavailable, match="not connected"):
        transport.write(b"value")

    bridge.connected = True
    bridge.reads.append("not binary")
    with pytest.raises(PhoneUsbError, match="Unexpected Router read type"):
        transport.read()
