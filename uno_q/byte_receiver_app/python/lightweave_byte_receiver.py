"""Binary-safe storage and validation for the UNO Q optical byte receiver."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

MAX_PAYLOAD_BYTES = 2_048
CHUNK_BYTES = 32
REQUEST_ID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)


class ReceiverError(RuntimeError):
    """The receiver cannot safely accept or return a request."""


class BridgeLike(Protocol):
    def call(self, method: str, *args: object) -> object: ...


@dataclass(frozen=True, slots=True)
class ArmRequest:
    request_id: str
    expected_bytes: int
    source: str


def canonical_request_id(value: object) -> str:
    text = str(value)
    if REQUEST_ID.fullmatch(text) is None:
        raise ReceiverError("Request ID is not a canonical UUID.")
    if str(uuid.UUID(text)) != text:
        raise ReceiverError("Request ID is not canonical.")
    return text


def validate_expected_bytes(value: object) -> int:
    try:
        expected = int(value)
    except (TypeError, ValueError) as exc:
        raise ReceiverError("Expected byte count must be an integer.") from exc
    if not 1 <= expected <= MAX_PAYLOAD_BYTES:
        raise ReceiverError("Expected byte count must be between 1 and 2,048.")
    return expected


def parse_arm_request(value: dict[str, Any], *, source: str) -> ArmRequest:
    if value.get("schema_version") != 1:
        raise ReceiverError("Unsupported arm-request schema version.")
    return ArmRequest(
        canonical_request_id(value.get("request_id")),
        validate_expected_bytes(value.get("expected_bytes")),
        source,
    )


def collect_received_bytes(bridge: BridgeLike, expected_bytes: int) -> bytes:
    expected = validate_expected_bytes(expected_bytes)
    received_count = int(bridge.call("get_received_byte_count"))
    if received_count != expected:
        raise ReceiverError(
            f"STM32 reports {received_count} bytes; expected {expected}."
        )
    output = bytearray()
    for offset in range(0, expected, CHUNK_BYTES):
        count = min(CHUNK_BYTES, expected - offset)
        raw = bridge.call("get_received_chunk", offset, count)
        text = "".join(str(raw).split())
        if len(text) != count * 2:
            raise ReceiverError(
                f"STM32 returned {len(text)} hexadecimal characters for "
                f"the {count}-byte chunk at offset {offset}."
            )
        try:
            chunk = bytes.fromhex(text)
        except ValueError as exc:
            raise ReceiverError("STM32 returned invalid hexadecimal data.") from exc
        output.extend(chunk)
    if len(output) != expected:
        raise ReceiverError("Collected payload length does not match the request.")
    return bytes(output)


class ReceiverStore:
    """Atomic filesystem control plane shared with the Windows verifier."""

    def __init__(self, app_root: Path) -> None:
        self.app_root = app_root
        self.data_root = app_root / "data"
        self.inbox = self.data_root / "inbox"
        self.processing = self.data_root / "processing"
        self.results = self.data_root / "results"
        self.state_path = self.data_root / "receiver-state.json"
        for path in (self.inbox, self.processing, self.results):
            path.mkdir(parents=True, exist_ok=True)

    def write_atomic_json(self, path: Path, value: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + ".partial")
        temporary.write_text(
            json.dumps(value, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def claim_next(self) -> ArmRequest | None:
        descriptors = sorted(self.inbox.glob("*.json"))
        if not descriptors:
            return None
        descriptor = descriptors[0]
        request_id = descriptor.stem
        if REQUEST_ID.fullmatch(request_id) is None:
            descriptor.unlink(missing_ok=True)
            return None
        claimed = self.processing / descriptor.name
        try:
            os.replace(descriptor, claimed)
        except FileNotFoundError:
            return None
        try:
            value = json.loads(claimed.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ReceiverError("Arm request must be a JSON object.")
            request = parse_arm_request(value, source="adb")
            if request.request_id != request_id:
                raise ReceiverError("Arm request filename and request ID differ.")
            return request
        except (json.JSONDecodeError, OSError, ReceiverError) as exc:
            self.write_error(request_id, str(exc))
            return None
        finally:
            claimed.unlink(missing_ok=True)

    def write_state(self, request: ArmRequest | None, status: str) -> None:
        value: dict[str, Any] = {
            "schema_version": 1,
            "status": status,
            "maximum_payload_bytes": MAX_PAYLOAD_BYTES,
        }
        if request is not None:
            value.update(
                request_id=request.request_id,
                expected_bytes=request.expected_bytes,
                source=request.source,
            )
        self.write_atomic_json(self.state_path, value)

    def write_error(self, request_id: str, message: str) -> None:
        self.write_atomic_json(
            self.results / f"{request_id}.json",
            {
                "schema_version": 1,
                "request_id": request_id,
                "accepted": False,
                "status": "error",
                "error": message,
            },
        )

    def write_result(
        self,
        request: ArmRequest,
        payload: bytes,
        *,
        stop_bit_valid: bool,
    ) -> dict[str, Any]:
        payload_path = self.results / f"{request.request_id}.bin"
        temporary = payload_path.with_suffix(".bin.partial")
        temporary.write_bytes(payload)
        os.replace(temporary, payload_path)
        result: dict[str, Any] = {
            "schema_version": 1,
            "request_id": request.request_id,
            "accepted": True,
            "status": "completed",
            "expected_bytes": request.expected_bytes,
            "received_bytes": len(payload),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "stop_bit_valid": stop_bit_valid,
            "bit_duration_ms": 25,
            "wire_format": "start-high/raw-msb-first/stop-low",
        }
        self.write_atomic_json(self.results / f"{request.request_id}.json", result)
        self.write_state(request, "completed")
        return result


def app_root() -> Path:
    configured = os.environ.get("APP_HOME")
    configured_path = Path(configured) if configured else None
    if configured_path is not None and configured_path.is_dir():
        return configured_path
    return Path(__file__).resolve().parents[1]
