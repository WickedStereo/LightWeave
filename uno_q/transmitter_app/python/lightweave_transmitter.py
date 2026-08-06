"""Atomic App Lab inbox for the LightWeave UNO Q laser transmitter."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

MAX_PAYLOAD_BYTES = 2_048
AUDIO_CHUNK_BYTES = 188
MAX_AUDIO_BYTES = 940
SAMPLES_PER_AUDIO_CHUNK = 24_000
BIT_DURATION_MS = 25
WIRE_OVERHEAD_BITS = 2
IMAGE_PRESETS = {
    "I64-Q1": 128,
    "I64-Q1-B128": 128,
    "I128-Q1-B768": 768,
    "I256-Q1-B2048": 2_048,
}
AUDIO_PRESET = re.compile(r"A1-E15-S([1-9][0-9]*)")
REQUEST_ID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)


class TransmitterError(RuntimeError):
    """A request cannot be safely submitted to the transmitter."""


class BridgeLike(Protocol):
    def call(self, method: str, *args: object) -> object: ...

    def notify(self, method: str, *args: object) -> None: ...


@dataclass(frozen=True, slots=True)
class Request:
    request_id: str
    media_type: str
    preset_code: str
    payload_bytes: int
    payload_sha256: str


def _canonical_request_id(value: object) -> str:
    text = str(value)
    if REQUEST_ID.fullmatch(text) is None:
        raise TransmitterError("Request ID is not a canonical UUID.")
    if str(uuid.UUID(text)) != text:
        raise TransmitterError("Request ID is not canonical.")
    return text


def _validate_audio(payload: bytes, preset_code: str) -> None:
    match = AUDIO_PRESET.fullmatch(preset_code)
    if match is None:
        raise TransmitterError("Malformed audio preset; expected A1-E15-S<n>.")
    if len(payload) > MAX_AUDIO_BYTES:
        raise TransmitterError("Raw audio exceeds the five-second/940-byte limit.")
    if len(payload) % AUDIO_CHUNK_BYTES:
        raise TransmitterError("Raw audio size must be divisible by 188 bytes.")
    chunk_count = len(payload) // AUDIO_CHUNK_BYTES
    samples = int(match.group(1))
    minimum = (chunk_count - 1) * SAMPLES_PER_AUDIO_CHUNK + 1
    maximum = chunk_count * SAMPLES_PER_AUDIO_CHUNK
    if not minimum <= samples <= maximum:
        raise TransmitterError("Audio sample count is impossible for the payload size.")
    for offset in range(0, len(payload), AUDIO_CHUNK_BYTES):
        if payload[offset + AUDIO_CHUNK_BYTES - 1] & 0xF0:
            raise TransmitterError("Raw audio chunk has non-zero padding bits.")


def validate_request(metadata: dict[str, Any], payload: bytes) -> Request:
    if metadata.get("schema_version") != 1:
        raise TransmitterError("Unsupported request schema version.")
    request = Request(
        request_id=_canonical_request_id(metadata.get("request_id")),
        media_type=str(metadata.get("media_type", "")),
        preset_code=str(metadata.get("preset_code", "")),
        payload_bytes=int(metadata.get("payload_bytes", -1)),
        payload_sha256=str(metadata.get("payload_sha256", "")).lower(),
    )
    if not payload:
        raise TransmitterError("Payload is empty.")
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise TransmitterError("Payload exceeds the 2,048-byte transmitter buffer.")
    if request.payload_bytes != len(payload):
        raise TransmitterError("Declared payload length does not match the file.")
    digest = hashlib.sha256(payload).hexdigest()
    if request.payload_sha256 != digest:
        raise TransmitterError("Payload SHA-256 does not match the request.")
    if request.media_type == "image":
        maximum = IMAGE_PRESETS.get(request.preset_code)
        if maximum is None:
            raise TransmitterError("Unsupported raw image preset.")
        if len(payload) > maximum:
            raise TransmitterError("Raw image exceeds its selected preset budget.")
    elif request.media_type == "audio":
        _validate_audio(payload, request.preset_code)
    else:
        raise TransmitterError("Media type must be image or audio.")
    return request


def transmission_seconds(payload_bytes: int) -> float:
    return (payload_bytes * 8 + WIRE_OVERHEAD_BITS) * BIT_DURATION_MS / 1_000


class InboxWorker:
    """Claim one request at a time and hand its bytes to RouterBridge."""

    def __init__(self, app_root: Path, bridge: BridgeLike) -> None:
        self.app_root = app_root
        self.bridge = bridge
        self.data_root = app_root / "data"
        self.inbox = self.data_root / "inbox"
        self.processing = self.data_root / "processing"
        self.results = self.data_root / "results"
        self.state_path = self.data_root / "transmitter-state.json"
        for path in (self.inbox, self.processing, self.results):
            path.mkdir(parents=True, exist_ok=True)

    def _state(self) -> dict[str, Any]:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _write_atomic(self, path: Path, value: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + ".partial")
        temporary.write_text(
            json.dumps(value, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def _write_result(self, request_id: str, value: dict[str, Any]) -> None:
        self._write_atomic(
            self.results / f"{request_id}.json",
            {"schema_version": 1, "request_id": request_id, **value},
        )

    def status(self, now: float | None = None) -> dict[str, Any]:
        current = time.time() if now is None else now
        state = self._state()
        busy_until = float(state.get("busy_until_epoch", 0.0))
        return {
            "ready": True,
            "app": "lightweave_transmitter",
            "maximum_payload_bytes": MAX_PAYLOAD_BYTES,
            "bit_duration_ms": BIT_DURATION_MS,
            "busy": busy_until > current,
            "busy_remaining_seconds": max(0.0, busy_until - current),
            "active_request_id": (
                state.get("request_id") if busy_until > current else None
            ),
        }

    def process_once(self, now: float | None = None) -> bool:
        candidates = sorted(self.inbox.glob("*.json"))
        if not candidates:
            return False
        descriptor = candidates[0]
        request_id = descriptor.stem
        if REQUEST_ID.fullmatch(request_id) is None:
            descriptor.unlink(missing_ok=True)
            return True
        claimed = self.processing / descriptor.name
        try:
            os.replace(descriptor, claimed)
        except FileNotFoundError:
            return False
        payload_path = self.inbox / f"{request_id}.bin"
        try:
            if (self.results / f"{request_id}.json").exists():
                raise TransmitterError("Duplicate request ID.")
            metadata = json.loads(claimed.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                raise TransmitterError("Request metadata must be an object.")
            payload = payload_path.read_bytes()
            request = validate_request(metadata, payload)
            current = time.time() if now is None else now
            status = self.status(current)
            if status["busy"]:
                raise TransmitterError(
                    "Transmitter is busy for approximately "
                    f"{status['busy_remaining_seconds']:.1f} more seconds."
                )

            if not self.bridge.call("prepare_image_buffer", len(payload)):
                raise TransmitterError("STM32 rejected the payload length.")
            for index, byte_value in enumerate(payload):
                if not self.bridge.call("store_image_byte", index, byte_value):
                    raise TransmitterError(f"STM32 rejected payload byte {index}.")
            buffered = int(self.bridge.call("get_loaded_byte_count"))
            if buffered != len(payload):
                raise TransmitterError(
                    f"STM32 reports {buffered} buffered bytes; expected {len(payload)}."
                )

            duration = transmission_seconds(len(payload))
            launch_time = current if now is not None else time.time()
            busy_until = launch_time + duration
            self.bridge.notify("transmit_image")
            result = {
                "accepted": True,
                "status": "accepted",
                "adapter": "uno-q-app-lab-adb",
                "media_type": request.media_type,
                "preset_code": request.preset_code,
                "payload_bytes": len(payload),
                "payload_sha256": request.payload_sha256,
                "buffered_bytes": buffered,
                "optical_bits": len(payload) * 8 + WIRE_OVERHEAD_BITS,
                "bit_duration_ms": BIT_DURATION_MS,
                "estimated_transmission_seconds": duration,
                "busy_until_epoch": busy_until,
                "completion_claimed": False,
            }
            self._write_atomic(
                self.state_path,
                {"request_id": request.request_id, "busy_until_epoch": busy_until},
            )
            self._write_result(request.request_id, result)
        except (
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            TransmitterError,
        ) as exc:
            safe_id = (
                request_id
                if REQUEST_ID.fullmatch(request_id)
                else str(uuid.uuid4())
            )
            self._write_result(
                safe_id,
                {
                    "accepted": False,
                    "status": "error",
                    "error": str(exc),
                },
            )
        finally:
            claimed.unlink(missing_ok=True)
            payload_path.unlink(missing_ok=True)
        return True


def app_root() -> Path:
    configured = os.environ.get("APP_HOME")
    configured_path = Path(configured) if configured else None
    if configured_path is not None and configured_path.is_dir():
        return configured_path
    return Path(__file__).resolve().parents[1]
