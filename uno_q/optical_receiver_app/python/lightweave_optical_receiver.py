"""Validated one-shot control plane for the LightWeave LWF1 receiver."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

try:
    from lightweave_optical_frame import (
        HEADER_BYTES,
        Header,
        crc16_ccitt_false,
        parse_header,
        validate_contract,
    )
except ModuleNotFoundError:  # Repository test environment.
    from lightweave.optical_frame import (
        HEADER_BYTES,
        Header,
        crc16_ccitt_false,
        parse_header,
        validate_contract,
    )

MAX_PAYLOAD_BYTES = 2_048
CHUNK_BYTES = 32
LISTEN_SCHEMA_VERSION = 2
REQUEST_ID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)


class ReceiverError(RuntimeError):
    """Safe receiver error surfaced through App Lab and ADB results."""


class RejectedFrameError(ReceiverError):
    """A complete but invalid frame, with diagnostic bytes preserved."""

    def __init__(
        self, message: str, payload: bytes, evidence: dict[str, Any]
    ) -> None:
        super().__init__(message)
        self.payload = payload
        self.evidence = evidence


class BridgeLike(Protocol):
    def call(self, method: str, *args: object) -> object: ...


@dataclass(frozen=True, slots=True)
class ReceiveRequest:
    request_id: str
    source: str


@dataclass(frozen=True, slots=True)
class ReceivedFrame:
    header: Header
    header_bytes: bytes
    payload: bytes
    received_crc: int
    computed_crc: int
    stop_bit_valid: bool


def canonical_request_id(value: object) -> str:
    text = str(value)
    if REQUEST_ID.fullmatch(text) is None:
        raise ReceiverError("Request ID is not a canonical UUID.")
    if str(uuid.UUID(text)) != text:
        raise ReceiverError("Request ID is not canonical.")
    return text


def build_request(request_id: object, *, source: str) -> ReceiveRequest:
    return ReceiveRequest(canonical_request_id(request_id), source)


def parse_listen_request(value: dict[str, Any], *, source: str) -> ReceiveRequest:
    if value.get("schema_version") != LISTEN_SCHEMA_VERSION:
        raise ReceiverError("Unsupported listen-request schema version.")
    if value.get("action") != "listen-lwf1":
        raise ReceiverError("Listen request must select the LWF1 receiver.")
    return build_request(value.get("request_id"), source=source)


def collect_received_bytes(bridge: BridgeLike, expected_bytes: int) -> bytes:
    if not 1 <= expected_bytes <= MAX_PAYLOAD_BYTES:
        raise ReceiverError("Declared byte count is outside the receiver buffer.")
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
    return bytes(output)


def collect_received_frame(bridge: BridgeLike) -> ReceivedFrame:
    error_code = str(bridge.call("get_receiver_error_code"))
    header_text = "".join(str(bridge.call("get_frame_header")).split())
    if error_code and error_code != "none" and len(header_text) != HEADER_BYTES * 2:
        raise ReceiverError(f"Optical frame rejected by STM32: {error_code}.")
    if len(header_text) != HEADER_BYTES * 2:
        raise ReceiverError("STM32 returned an invalid LWF1 header.")
    try:
        header_bytes = bytes.fromhex(header_text)
    except ValueError as exc:
        raise ReceiverError("STM32 returned non-hexadecimal LWF1 header data.") from exc
    try:
        header = parse_header(header_bytes)
    except ValueError as exc:
        if error_code and error_code != "none":
            raise ReceiverError(
                f"Optical frame rejected by STM32: {error_code}."
            ) from exc
        raise ReceiverError(str(exc)) from exc
    payload = collect_received_bytes(bridge, header.payload_bytes)
    received_crc = int(bridge.call("get_received_crc"))
    computed_crc = int(bridge.call("get_computed_crc"))
    python_crc = crc16_ccitt_false(header_bytes + payload)
    stop_bit_valid = bool(bridge.call("get_stop_bit_valid"))
    if error_code and error_code != "none":
        evidence = {
            "error_code": error_code,
            "header_hex": header_bytes.hex(),
            "profile_id": header.profile.profile_id,
            "preset_code": header.preset_code,
            "media_parameter": header.media_parameter,
            "received_bytes": len(payload),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "received_crc16": received_crc,
            "computed_crc16": computed_crc,
            "python_crc16": python_crc,
            "stop_bit_valid": stop_bit_valid,
        }
        raise RejectedFrameError(
            f"Optical frame rejected by STM32: {error_code}; "
            f"wire CRC 0x{received_crc:04x}, computed 0x{computed_crc:04x}.",
            payload,
            evidence,
        )
    try:
        validate_contract(
            header.profile,
            header.payload_bytes,
            header.media_parameter,
            payload,
        )
    except ValueError as exc:
        raise ReceiverError(str(exc)) from exc
    if received_crc != computed_crc or received_crc != python_crc:
        raise ReceiverError(
            "LWF1 CRC mismatch between wire, STM32, and Linux validation."
        )
    if not stop_bit_valid:
        raise ReceiverError("The optical stop bit was invalid.")
    return ReceivedFrame(
        header,
        header_bytes,
        payload,
        received_crc,
        computed_crc,
        stop_bit_valid,
    )


class ReceiverStore:
    """Atomic filesystem control plane shared with Windows verifiers."""

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
                raise ReceiverError("Listen request must be a JSON object.")
            request = parse_listen_request(value, source="adb")
            if request.request_id != request_id:
                raise ReceiverError("Listen request filename and request ID differ.")
            return request
        except (json.JSONDecodeError, OSError, ReceiverError) as exc:
            self.write_error(request_id, str(exc))
            return None
        finally:
            claimed.unlink(missing_ok=True)

    def write_state(self, request: ReceiveRequest | None, status: str) -> None:
        value: dict[str, Any] = {
            "schema_version": LISTEN_SCHEMA_VERSION,
            "status": status,
            "wire_format": "LWF1",
            "maximum_payload_bytes": MAX_PAYLOAD_BYTES,
        }
        if request is not None:
            value.update(request_id=request.request_id, source=request.source)
        self.write_atomic_json(self.state_path, value)

    def write_error(
        self,
        request_id: str,
        message: str,
        *,
        evidence: dict[str, Any] | None = None,
        payload: bytes | None = None,
    ) -> None:
        if payload is not None:
            self.write_atomic(self.results / f"{request_id}.rejected.bin", payload)
        value: dict[str, Any] = {
            "schema_version": LISTEN_SCHEMA_VERSION,
            "request_id": request_id,
            "accepted": False,
            "status": "error",
            "error": message,
        }
        if evidence is not None:
            value["frame_evidence"] = evidence
        self.write_atomic_json(
            self.results / f"{request_id}.json",
            value,
        )

    def write_result(
        self,
        request: ReceiveRequest,
        frame: ReceivedFrame,
        media: bytes,
        *,
        output_extension: str,
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        payload_path = self.results / f"{request.request_id}.bin"
        media_path = self.results / f"{request.request_id}.{output_extension}"
        self.write_atomic(payload_path, frame.payload)
        self.write_atomic(media_path, media)
        header = frame.header
        result: dict[str, Any] = {
            "schema_version": LISTEN_SCHEMA_VERSION,
            "request_id": request.request_id,
            "accepted": True,
            "status": "completed",
            "wire_format": "LWF1",
            "frame_version": 1,
            "media_type": header.profile.media_type,
            "profile_id": header.profile.profile_id,
            "preset_code": header.preset_code,
            "payload_bytes": len(frame.payload),
            "received_bytes": len(frame.payload),
            "payload_sha256": hashlib.sha256(frame.payload).hexdigest(),
            "media_parameter": header.media_parameter,
            "header_hex": frame.header_bytes.hex(),
            "received_crc16": frame.received_crc,
            "computed_crc16": frame.computed_crc,
            "wire_crc_hex": frame.received_crc.to_bytes(2, "little").hex(),
            "crc_valid": True,
            "stop_bit_valid": frame.stop_bit_valid,
            "bit_duration_ms": 25,
            "reconstruction": metrics,
            "output_extension": output_extension,
        }
        self.write_atomic_json(self.results / f"{request.request_id}.json", result)
        self.write_state(request, "completed")
        return result


def app_root() -> Path:
    configured = os.environ.get("APP_HOME")
    if configured and Path(configured).is_dir():
        return Path(configured)
    return Path(__file__).resolve().parents[1]
