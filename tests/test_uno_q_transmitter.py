from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from lightweave.uno_q_transport import (
    UnoQAdbSink,
    UnoQTransportError,
    validate_uno_q_payload,
)

TRANSMITTER_PYTHON = (
    Path(__file__).resolve().parents[1] / "uno_q" / "transmitter_app" / "python"
)
sys.path.insert(0, str(TRANSMITTER_PYTHON))

import lightweave_transmitter as tx  # noqa: E402


class FakeBridge:
    def __init__(self) -> None:
        self.expected = 0
        self.values: list[int | None] = []
        self.notifications: list[str] = []

    def call(self, method: str, *args: object) -> object:
        if method == "prepare_image_buffer":
            self.expected = int(args[0])
            self.values = [None] * self.expected
            return True
        if method == "store_image_byte":
            index, value = (int(item) for item in args)
            self.values[index] = value
            return True
        if method == "get_loaded_byte_count":
            return sum(value is not None for value in self.values)
        raise AssertionError(method)

    def notify(self, method: str, *args: object) -> None:
        assert not args
        self.notifications.append(method)


def _publish(
    root: Path,
    payload: bytes,
    *,
    media_type: str = "image",
    preset_code: str = "I128-Q1-B768",
    digest: str | None = None,
) -> str:
    request_id = str(uuid.uuid4())
    inbox = root / "data" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / f"{request_id}.bin").write_bytes(payload)
    metadata = {
        "schema_version": 1,
        "request_id": request_id,
        "media_type": media_type,
        "preset_code": preset_code,
        "payload_bytes": len(payload),
        "payload_sha256": digest or hashlib.sha256(payload).hexdigest(),
    }
    (inbox / f"{request_id}.json").write_text(json.dumps(metadata), encoding="utf-8")
    return request_id


def test_inbox_preserves_every_binary_value(tmp_path: Path) -> None:
    bridge = FakeBridge()
    worker = tx.InboxWorker(tmp_path, bridge)
    payload = bytes(range(256))
    request_id = _publish(tmp_path, payload)

    assert worker.process_once(now=1_000.0)
    result = json.loads(
        (tmp_path / "data" / "results" / f"{request_id}.json").read_text()
    )
    assert result["accepted"] is True
    assert result["payload_bytes"] == 256
    assert result["buffered_bytes"] == 256
    assert bytes(bridge.values) == payload
    assert bridge.notifications == ["transmit_image"]
    assert not list((tmp_path / "data" / "inbox").iterdir())


def test_inbox_rejects_hash_mismatch_without_notifying(tmp_path: Path) -> None:
    bridge = FakeBridge()
    worker = tx.InboxWorker(tmp_path, bridge)
    request_id = _publish(tmp_path, b"payload", digest="0" * 64)
    worker.process_once(now=1_000.0)
    result = json.loads(
        (tmp_path / "data" / "results" / f"{request_id}.json").read_text()
    )
    assert result["accepted"] is False
    assert "SHA-256" in result["error"]
    assert bridge.notifications == []


def test_inbox_ignores_partial_requests_and_rejects_busy(tmp_path: Path) -> None:
    bridge = FakeBridge()
    worker = tx.InboxWorker(tmp_path, bridge)
    partial = worker.inbox / f"{uuid.uuid4()}.json.partial"
    partial.write_text("{}", encoding="utf-8")
    assert worker.process_once(now=2_000.0) is False

    first = _publish(tmp_path, bytes(16))
    worker.process_once(now=2_000.0)
    assert json.loads((worker.results / f"{first}.json").read_text())["accepted"]
    second = _publish(tmp_path, bytes(16))
    worker.process_once(now=2_000.1)
    result = json.loads((worker.results / f"{second}.json").read_text())
    assert result["accepted"] is False
    assert "busy" in result["error"]


@pytest.mark.parametrize(
    "payload,media,preset,message",
    [
        (b"", "image", "I64-Q1-B128", "empty"),
        (bytes(129), "image", "I64-Q1-B128", "128-byte"),
        (bytes(187), "audio", "A1-E15-S24000", "divisible"),
        (bytes(188), "audio", "A1-E15-S24001", "impossible"),
        (bytes(941), "audio", "A1-E15-S120000", "940-byte"),
    ],
)
def test_host_contract_rejects_invalid_payloads(
    payload: bytes, media: str, preset: str, message: str
) -> None:
    with pytest.raises(UnoQTransportError, match=message):
        validate_uno_q_payload(payload, media, preset)


class FakeAdb:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.uploaded: bytes | None = None
        self.commands: list[list[str]] = []

    def __call__(
        self, command: list[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        if command[-2:] == ["devices", "-l"]:
            return subprocess.CompletedProcess(
                command, 0, "List of devices attached\nuno\tdevice\n", ""
            )
        if command[-3:] == ["shell", "uname", "-m"]:
            return subprocess.CompletedProcess(command, 0, "aarch64\n", "")
        if command[-3:] == ["shell", "arduino-app-cli", "version"]:
            return subprocess.CompletedProcess(
                command, 0, "Arduino App CLI version 0.12.1\n", ""
            )
        if command[-6:] == [
            "shell",
            "arduino-app-cli",
            "--format",
            "json",
            "app",
            "list",
        ]:
            value = {"apps": [{"name": "lightweave_transmitter", "status": "running"}]}
            return subprocess.CompletedProcess(command, 0, json.dumps(value), "")
        if "test" in command and "transmitter.manifest.json" in command[-1]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[-3:-1] == ["exec-out", "cat"] and command[-1].endswith(
            "transmitter-state.json"
        ):
            return subprocess.CompletedProcess(command, 1, "", "not found")
        if command[-3:-1] == ["test", "-s"] and "/results/" in command[-1]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if "push" in command:
            source = Path(command[-2])
            if source.name == "payload.bin":
                self.uploaded = source.read_bytes()
            return subprocess.CompletedProcess(command, 0, "pushed", "")
        if command[-3:-1] == ["exec-out", "cat"] and "/results/" in command[-1]:
            request_id = Path(command[-1]).stem
            evidence = {
                "schema_version": 1,
                "request_id": request_id,
                "accepted": True,
                "adapter": "uno-q-app-lab-adb",
                "payload_sha256": hashlib.sha256(self.payload).hexdigest(),
                "payload_bytes": len(self.payload),
                "buffered_bytes": len(self.payload),
                "optical_bits": len(self.payload) * 8 + 2,
                "estimated_transmission_seconds": tx.transmission_seconds(
                    len(self.payload)
                ),
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(evidence), "")
        return subprocess.CompletedProcess(command, 0, "", "")


def test_adb_sink_pushes_exact_binary_payload(tmp_path: Path) -> None:
    adb = tmp_path / "adb.exe"
    adb.write_bytes(b"stub")
    payload = bytes(range(128))
    runner = FakeAdb(payload)
    sink = UnoQAdbSink(
        media_type="image",
        preset_code="I64-Q1-B128",
        adb_path=adb,
        runner=runner,
        sleep=lambda _: None,
    )
    receipt = sink.send(payload)
    assert runner.uploaded == payload
    assert receipt.bytes_sent == 128
    assert receipt.evidence["buffered_bytes"] == 128


def test_adb_sink_rejects_missing_device(tmp_path: Path) -> None:
    adb = tmp_path / "adb.exe"
    adb.write_bytes(b"stub")

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "List of devices attached\n", "")

    sink = UnoQAdbSink(
        media_type="image",
        preset_code="I64-Q1-B128",
        adb_path=adb,
        runner=runner,
    )
    with pytest.raises(UnoQTransportError, match="exactly one"):
        sink.status()
