"""Validated control plane for the LightWeave optical image receiver."""

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
PRESET_BUDGETS = {
    "I64-Q1-B128": 128,
    "I128-Q1-B768": 768,
    "I256-Q1-B2048": 2_048,
}
REQUEST_ID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)


class ReceiverError(RuntimeError):
    """Safe receiver error surfaced through App Lab and ADB results."""


class BridgeLike(Protocol):
    def call(self, method: str, *args: object) -> object: ...


@dataclass(frozen=True, slots=True)
class ReceiveRequest:
    request_id: str
    preset_code: str
    expected_bytes: int
    source: str


def canonical_request_id(value: object) -> str:
    text = str(value)
    if REQUEST_ID.fullmatch(text) is None:
        raise ReceiverError("Request ID is not a canonical UUID.")
    if str(uuid.UUID(text)) != text:
        raise ReceiverError("Request ID is not canonical.")
    return text


def validate_preset(value: object) -> str:
    code = str(value)
    if code not in PRESET_BUDGETS:
        raise ReceiverError("Unsupported raw image preset.")
    return code


def validate_expected_bytes(value: object, preset_code: str) -> int:
    try:
        expected = int(value)
    except (TypeError, ValueError) as exc:
        raise ReceiverError("Expected byte count must be an integer.") from exc
    maximum = PRESET_BUDGETS[validate_preset(preset_code)]
    if not 1 <= expected <= maximum:
        raise ReceiverError(
            f"Expected byte count must be between 1 and {maximum} for "
            f"{preset_code}."
        )
    return expected


def build_request(
    request_id: object,
    preset_code: object,
    expected_bytes: object,
    *,
    source: str,
) -> ReceiveRequest:
    preset = validate_preset(preset_code)
    return ReceiveRequest(
        canonical_request_id(request_id),
        preset,
        validate_expected_bytes(expected_bytes, preset),
        source,
    )


def parse_arm_request(value: dict[str, Any], *, source: str) -> ReceiveRequest:
    if value.get("schema_version") != 1:
        raise ReceiverError("Unsupported arm-request schema version.")
    if value.get("media_type") != "image":
        raise ReceiverError("The optical receiver currently accepts images only.")
    return build_request(
        value.get("request_id"),
        value.get("preset_code"),
        value.get("expected_bytes"),
        source=source,
    )


def collect_received_bytes(bridge: BridgeLike, expected_bytes: int) -> bytes:
    if not 1 <= expected_bytes <= MAX_PAYLOAD_BYTES:
        raise ReceiverError("Expected byte count is outside the receiver buffer.")
    received_count = int(bridge.call("get_received_byte_count"))
    if received_count != expected_bytes:
        raise ReceiverError(
            f"STM32 reports {received_count} bytes; expected {expected_bytes}."
        )
    output = bytearray()
    for offset in range(0, expected_bytes, CHUNK_BYTES):
        count = min(CHUNK_BYTES, expected_bytes - offset)
        text = "".join(
            str(bridge.call("get_received_chunk", offset, count)).split()
        )
        if len(text) != count * 2:
            raise ReceiverError(
                f"STM32 returned an invalid chunk at byte offset {offset}."
            )
        try:
            output.extend(bytes.fromhex(text))
        except ValueError as exc:
            raise ReceiverError("STM32 returned invalid hexadecimal data.") from exc
    if len(output) != expected_bytes:
        raise ReceiverError("Collected payload length does not match the request.")
    return bytes(output)


class ReceiverStore:
    """Atomic filesystem control plane shared with the Windows verifier."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.data_root = root / "data"
        self.inbox = self.data_root / "inbox"
        self.processing = self.data_root / "processing"
        self.results = self.data_root / "results"
        self.state_path = self.data_root / "receiver-state.json"
        for path in (self.inbox, self.processing, self.results):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def write_atomic(path: Path, data: bytes) -> None:
        temporary = path.with_suffix(path.suffix + ".partial")
        temporary.write_bytes(data)
        os.replace(temporary, path)

    def write_atomic_json(self, path: Path, value: dict[str, Any]) -> None:
        self.write_atomic(
            path,
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode(),
        )

    def claim_next(self) -> ReceiveRequest | None:
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

    def write_state(self, request: ReceiveRequest | None, status: str) -> None:
        value: dict[str, Any] = {
            "schema_version": 1,
            "status": status,
            "media_type": "image",
            "maximum_payload_bytes": MAX_PAYLOAD_BYTES,
        }
        if request is not None:
            value.update(
                request_id=request.request_id,
                preset_code=request.preset_code,
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
        request: ReceiveRequest,
        payload: bytes,
        png: bytes,
        *,
        stop_bit_valid: bool,
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        self.write_atomic(self.results / f"{request.request_id}.bin", payload)
        self.write_atomic(self.results / f"{request.request_id}.png", png)
        result: dict[str, Any] = {
            "schema_version": 1,
            "request_id": request.request_id,
            "accepted": True,
            "status": "completed",
            "media_type": "image",
            "preset_code": request.preset_code,
            "expected_bytes": request.expected_bytes,
            "received_bytes": len(payload),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "stop_bit_valid": stop_bit_valid,
            "bit_duration_ms": 25,
            "wire_format": "start-high/raw-msb-first/stop-low",
            "reconstruction": metrics,
        }
        self.write_atomic_json(self.results / f"{request.request_id}.json", result)
        self.write_state(request, "completed")
        return result


def app_root() -> Path:
    configured = os.environ.get("APP_HOME")
    if configured and Path(configured).is_dir():
        return Path(configured)
    return Path(__file__).resolve().parents[1]

