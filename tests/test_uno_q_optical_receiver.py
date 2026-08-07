from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[1] / "uno_q" / "optical_receiver_app"
APP_PYTHON = APP_ROOT / "python"
sys.path.insert(0, str(APP_PYTHON))

import lightweave_optical_receiver as optical  # noqa: E402


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


def test_request_requires_image_preset_and_matching_budget() -> None:
    request_id = str(uuid.uuid4())
    request = optical.parse_arm_request(
        {
            "schema_version": 1,
            "request_id": request_id,
            "media_type": "image",
            "preset_code": "I128-Q1-B768",
            "expected_bytes": 216,
        },
        source="test",
    )
    assert request == optical.ReceiveRequest(
        request_id, "I128-Q1-B768", 216, "test"
    )
    with pytest.raises(optical.ReceiverError, match="between 1 and 128"):
        optical.build_request(
            request_id, "I64-Q1-B128", 129, source="test"
        )
    with pytest.raises(optical.ReceiverError, match="images only"):
        optical.parse_arm_request(
            {
                "schema_version": 1,
                "request_id": request_id,
                "media_type": "audio",
                "preset_code": "I64-Q1-B128",
                "expected_bytes": 1,
            },
            source="test",
        )


def test_collect_preserves_every_byte_value_in_chunks() -> None:
    payload = bytes(range(256))
    bridge = FakeBridge(payload)
    assert optical.collect_received_bytes(bridge, len(payload)) == payload
    assert bridge.chunks == [(offset, 32) for offset in range(0, 256, 32)]


def test_collect_rejects_reported_length_mismatch() -> None:
    with pytest.raises(optical.ReceiverError, match="reports 3 bytes"):
        optical.collect_received_bytes(FakeBridge(b"abcd", reported_count=3), 4)


def test_store_claims_request_and_records_reconstruction(tmp_path: Path) -> None:
    store = optical.ReceiverStore(tmp_path)
    request_id = str(uuid.uuid4())
    descriptor = {
        "schema_version": 1,
        "request_id": request_id,
        "media_type": "image",
        "preset_code": "I64-Q1-B128",
        "expected_bytes": 4,
    }
    (store.inbox / f"{request_id}.json").write_text(
        json.dumps(descriptor), encoding="utf-8"
    )
    request = store.claim_next()
    assert request == optical.ReceiveRequest(
        request_id, "I64-Q1-B128", 4, "adb"
    )
    payload = b"\x00\xff\xaa\x55"
    png = b"\x89PNG\r\n\x1a\nfixture"
    metrics = {
        "backend": "ncnn-vulkan",
        "device": "Turnip Adreno 702",
        "strict_no_fallback": True,
    }
    result = store.write_result(
        request,
        payload,
        png,
        stop_bit_valid=True,
        metrics=metrics,
    )
    assert result["payload_sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["reconstruction"] == metrics
    assert (store.results / f"{request_id}.bin").read_bytes() == payload
    assert (store.results / f"{request_id}.png").read_bytes() == png


def test_invalid_filename_request_id_is_not_processed(tmp_path: Path) -> None:
    store = optical.ReceiverStore(tmp_path)
    (store.inbox / "not-a-uuid.json").write_text("{}", encoding="utf-8")
    assert store.claim_next() is None
    assert not list(store.processing.iterdir())


def test_tracked_app_preserves_wire_and_strict_decoder_contracts() -> None:
    sketch = (APP_ROOT / "sketch" / "sketch.ino").read_text(encoding="utf-8")
    main = (APP_ROOT / "python" / "main.py").read_text(encoding="utf-8")
    page = (APP_ROOT / "assets" / "index.html").read_text(encoding="utf-8")
    assert "bitDurationUs = 25000UL" in sketch
    assert "sensorPin = A0" in sketch
    assert 'Bridge.provide("start_receive"' in sketch
    assert "from lightweave_uno import decode_payload" in main
    assert "decode_payload(payload, request.preset_code)" in main
    assert "http://" not in page
    assert "https://" not in page
