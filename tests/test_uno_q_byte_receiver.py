from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path

import pytest

RECEIVER_ROOT = (
    Path(__file__).resolve().parents[1] / "uno_q" / "byte_receiver_app"
)
RECEIVER_PYTHON = RECEIVER_ROOT / "python"
sys.path.insert(0, str(RECEIVER_PYTHON))

import lightweave_byte_receiver as rx  # noqa: E402


class FakeBridge:
    def __init__(self, payload: bytes, *, reported_count: int | None = None) -> None:
        self.payload = payload
        self.reported_count = reported_count
        self.chunks: list[tuple[int, int]] = []

    def call(self, method: str, *args: object) -> object:
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
        raise AssertionError(method)


def test_collect_received_bytes_preserves_every_byte_value() -> None:
    payload = bytes(range(256))
    bridge = FakeBridge(payload)
    assert rx.collect_received_bytes(bridge, len(payload)) == payload
    assert bridge.chunks == [(offset, 32) for offset in range(0, 256, 32)]


def test_collect_received_bytes_rejects_count_mismatch() -> None:
    with pytest.raises(rx.ReceiverError, match="reports 3 bytes"):
        rx.collect_received_bytes(FakeBridge(b"abcd", reported_count=3), 4)


@pytest.mark.parametrize("value", [0, -1, 2049, "bad", None])
def test_expected_length_fails_closed(value: object) -> None:
    with pytest.raises(rx.ReceiverError):
        rx.validate_expected_bytes(value)


def test_store_claims_request_and_writes_binary_result(tmp_path: Path) -> None:
    store = rx.ReceiverStore(tmp_path)
    request_id = str(uuid.uuid4())
    descriptor = {
        "schema_version": 1,
        "request_id": request_id,
        "expected_bytes": 4,
    }
    (store.inbox / f"{request_id}.json").write_text(
        json.dumps(descriptor), encoding="utf-8"
    )
    request = store.claim_next()
    assert request == rx.ArmRequest(request_id, 4, "adb")
    payload = b"\x00\xff\xaa\x55"
    result = store.write_result(request, payload, stop_bit_valid=True)
    assert result["payload_sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["stop_bit_valid"] is True
    assert (store.results / f"{request_id}.bin").read_bytes() == payload
    assert json.loads(store.state_path.read_text())["status"] == "completed"


def test_store_rejects_filename_request_mismatch(tmp_path: Path) -> None:
    store = rx.ReceiverStore(tmp_path)
    filename_id = str(uuid.uuid4())
    descriptor = {
        "schema_version": 1,
        "request_id": str(uuid.uuid4()),
        "expected_bytes": 4,
    }
    (store.inbox / f"{filename_id}.json").write_text(
        json.dumps(descriptor), encoding="utf-8"
    )
    assert store.claim_next() is None
    result = json.loads((store.results / f"{filename_id}.json").read_text())
    assert result["accepted"] is False
    assert "filename" in result["error"]


def test_tracked_receiver_preserves_wire_contract_and_offline_ui() -> None:
    sketch = (RECEIVER_ROOT / "sketch" / "sketch.ino").read_text(encoding="utf-8")
    page = (RECEIVER_ROOT / "assets" / "index.html").read_text(encoding="utf-8")
    assert "bitDurationUs = 25000UL" in sketch
    assert "sensorPin = A0" in sketch
    assert 'Bridge.provide("start_receive"' in sketch
    assert 'Bridge.provide("get_received_chunk"' in sketch
    assert "http://" not in page
    assert "https://" not in page
