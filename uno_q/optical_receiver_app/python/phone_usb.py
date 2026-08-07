"""Durable decoded-result delivery through the UNO Q Router monitor."""

from __future__ import annotations

import json
import os
import queue
import struct
import time
import uuid
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAGIC = b"LWRX"
VERSION = 2
FLAGS = 0
HEADER_PREFIX = struct.Struct("<4sBBHII")
HEADER = struct.Struct("<4sBBHIII")
MAX_METADATA_BYTES = 256 * 1024
MAX_MEDIA_BYTES = 16 * 1024 * 1024
MEDIA_TYPES = {"text": 1, "image": 2, "audio": 3, "status": 4}
MEDIA_NAMES = {value: key for key, value in MEDIA_TYPES.items()}
CONTENT_TYPES = {
    "text": "text/plain; charset=utf-8",
    "image": "image/png",
    "audio": "audio/wav",
    "status": "application/json",
}
CONTROL_MAGIC = b"LWCT"
CONTROL_VERSION = 1
CONTROL_PREFIX = struct.Struct("<4sBBH")
CONTROL = struct.Struct("<4sBBHI")
CONTROL_COMMANDS = {"listen": 1, "cancel": 2, "status": 3}
CONTROL_NAMES = {value: key for key, value in CONTROL_COMMANDS.items()}


class PhoneUsbError(RuntimeError):
    """Decoded-result USB framing or delivery failed."""


class PhoneUsbUnavailable(PhoneUsbError):
    """The phone-facing CDC endpoint is not currently writable."""


@dataclass(frozen=True, slots=True)
class ParsedPhoneFrame:
    media_type: str
    metadata: dict[str, Any]
    payload: bytes
    crc32: int


class RouterMonitorTransport:
    """Use UNO Q's boot-managed serial monitor as the CDC byte transport."""

    name = "arduino-router-monitor"

    def __init__(self, bridge: Any, *, timeout_seconds: float = 2.0) -> None:
        self.bridge = bridge
        self.timeout_seconds = timeout_seconds
        self.last_error: str | None = None

    def connected(self) -> bool:
        try:
            value = self.bridge.call(
                "mon/connected",
                timeout=max(1, int(self.timeout_seconds)),
            )
        except Exception as exc:
            self.last_error = str(exc)
            return False
        connected = value is True
        self.last_error = (
            None if connected else "Router serial monitor is disconnected."
        )
        return connected

    def read(self, maximum_bytes: int = 4096) -> bytes:
        if not 1 <= maximum_bytes <= 65536:
            raise PhoneUsbError("Router monitor read size is invalid.")
        if not self.connected():
            raise PhoneUsbUnavailable(
                "UNO Q serial Router is not connected to the USB gadget service."
            )
        try:
            value = self.bridge.call(
                "mon/read",
                maximum_bytes,
                timeout=max(1, int(self.timeout_seconds)),
            )
        except Exception as exc:
            self.last_error = str(exc)
            raise PhoneUsbUnavailable(
                f"Could not read the UNO Q serial Router: {exc}."
            ) from exc
        if isinstance(value, bytes | bytearray | memoryview) or (
            isinstance(value, list)
            and all(isinstance(item, int) and 0 <= item <= 255 for item in value)
        ):
            data = bytes(value)
        else:
            self.last_error = f"Unexpected Router read type: {type(value).__name__}."
            raise PhoneUsbError(self.last_error)
        self.last_error = None
        return data

    def write(self, data: bytes, timeout_seconds: float | None = None) -> int:
        if not data:
            raise PhoneUsbError("Refusing to write an empty phone frame.")
        if not self.connected():
            raise PhoneUsbUnavailable(
                "UNO Q serial Router is not connected to the USB gadget service."
            )
        timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        try:
            written = self.bridge.call(
                "mon/write",
                data,
                timeout=max(1, int(timeout)),
            )
        except Exception as exc:
            self.last_error = str(exc)
            raise PhoneUsbUnavailable(
                f"Could not write through the UNO Q serial Router: {exc}."
            ) from exc
        if not isinstance(written, int) or written != len(data):
            self.last_error = (
                f"Router accepted {written!r} of {len(data)} phone frame bytes."
            )
            raise PhoneUsbError(self.last_error)
        self.last_error = None
        return written

    def status(self) -> dict[str, Any]:
        connected = self.connected()
        return {
            "transport": self.name,
            "router_connected": connected,
            "read_method": "mon/read",
            "write_method": "mon/write",
            "last_error": self.last_error,
        }


def _canonical_metadata(metadata: dict[str, Any]) -> bytes:
    encoded = json.dumps(
        metadata,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if not encoded or len(encoded) > MAX_METADATA_BYTES:
        raise PhoneUsbError("Phone metadata is empty or exceeds 256 KiB.")
    return encoded


def build_phone_frame(
    media_type: str,
    metadata: dict[str, Any],
    payload: bytes,
) -> bytes:
    type_id = MEDIA_TYPES.get(media_type)
    if type_id is None:
        raise PhoneUsbError(f"Unsupported phone media type: {media_type}.")
    if not payload or len(payload) > MAX_MEDIA_BYTES:
        raise PhoneUsbError("Phone media is empty or exceeds 16 MiB.")
    metadata_bytes = _canonical_metadata(metadata)
    prefix = HEADER_PREFIX.pack(
        MAGIC,
        VERSION,
        type_id,
        FLAGS,
        len(metadata_bytes),
        len(payload),
    )
    body = metadata_bytes + payload
    checksum = zlib.crc32(prefix + body) & 0xFFFFFFFF
    return prefix + struct.pack("<I", checksum) + body


def parse_phone_frame(frame: bytes) -> ParsedPhoneFrame:
    if len(frame) < HEADER.size:
        raise PhoneUsbError("Phone frame is truncated before its header.")
    magic, version, type_id, flags, metadata_size, payload_size, checksum = (
        HEADER.unpack_from(frame)
    )
    if magic != MAGIC:
        raise PhoneUsbError("Phone frame has invalid magic.")
    if version != VERSION:
        raise PhoneUsbError("Phone frame has an unsupported version.")
    if type_id not in MEDIA_NAMES:
        raise PhoneUsbError("Phone frame has an unsupported media type.")
    if flags != FLAGS:
        raise PhoneUsbError("Phone frame has unsupported flags.")
    if not 1 <= metadata_size <= MAX_METADATA_BYTES:
        raise PhoneUsbError("Phone frame metadata length is invalid.")
    if not 1 <= payload_size <= MAX_MEDIA_BYTES:
        raise PhoneUsbError("Phone frame media length is invalid.")
    expected = HEADER.size + metadata_size + payload_size
    if len(frame) != expected:
        raise PhoneUsbError("Phone frame length does not match its header.")
    prefix = frame[: HEADER_PREFIX.size]
    body = frame[HEADER.size :]
    computed = zlib.crc32(prefix + body) & 0xFFFFFFFF
    if computed != checksum:
        raise PhoneUsbError("Phone frame CRC-32 mismatch.")
    metadata_bytes = frame[HEADER.size : HEADER.size + metadata_size]
    try:
        metadata = json.loads(metadata_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhoneUsbError("Phone frame metadata is not valid UTF-8 JSON.") from exc
    if not isinstance(metadata, dict):
        raise PhoneUsbError("Phone frame metadata must be a JSON object.")
    return ParsedPhoneFrame(
        MEDIA_NAMES[type_id],
        metadata,
        frame[HEADER.size + metadata_size :],
        checksum,
    )


def build_control_frame(command: str) -> bytes:
    command_id = CONTROL_COMMANDS.get(command)
    if command_id is None:
        raise PhoneUsbError(f"Unsupported phone control command: {command}.")
    prefix = CONTROL_PREFIX.pack(
        CONTROL_MAGIC,
        CONTROL_VERSION,
        command_id,
        0,
    )
    return prefix + struct.pack("<I", zlib.crc32(prefix) & 0xFFFFFFFF)


def parse_control_frame(frame: bytes) -> str:
    if len(frame) != CONTROL.size:
        raise PhoneUsbError("Phone control frame must be exactly 12 bytes.")
    magic, version, command_id, flags, checksum = CONTROL.unpack(frame)
    if magic != CONTROL_MAGIC or version != CONTROL_VERSION or flags != 0:
        raise PhoneUsbError("Phone control frame header is invalid.")
    command = CONTROL_NAMES.get(command_id)
    if command is None:
        raise PhoneUsbError("Phone control command is unsupported.")
    if zlib.crc32(frame[: CONTROL_PREFIX.size]) & 0xFFFFFFFF != checksum:
        raise PhoneUsbError("Phone control frame CRC-32 mismatch.")
    return command


class PhoneControlReader:
    """Poll controls from the boot-managed Router monitor without device access."""

    def __init__(self, transport: RouterMonitorTransport) -> None:
        self.transport = transport
        self.buffer = bytearray()
        self.last_error: str | None = None
        self.commands: queue.Queue[str] = queue.Queue()
        self.running = False

    def _accept(self, data: bytes) -> None:
        self.buffer.extend(data)
        while True:
            magic_at = self.buffer.find(CONTROL_MAGIC)
            if magic_at < 0:
                if len(self.buffer) > len(CONTROL_MAGIC) - 1:
                    del self.buffer[: -(len(CONTROL_MAGIC) - 1)]
                break
            if magic_at:
                del self.buffer[:magic_at]
            if len(self.buffer) < CONTROL.size:
                break
            candidate = bytes(self.buffer[: CONTROL.size])
            try:
                command = parse_control_frame(candidate)
            except PhoneUsbError as exc:
                self.last_error = str(exc)
                del self.buffer[0]
                continue
            self.commands.put(command)
            del self.buffer[: CONTROL.size]

    def start(self) -> None:
        self.running = True

    def close(self) -> None:
        self.running = False

    def poll(self) -> list[str]:
        self.start()
        try:
            data = self.transport.read(4096)
            if data:
                print(f"Phone USB received {len(data)} control bytes", flush=True)
                self._accept(data)
            self.last_error = None
        except PhoneUsbUnavailable as exc:
            self.last_error = str(exc)
        except PhoneUsbError as exc:
            self.last_error = str(exc)
        commands: list[str] = []
        while True:
            try:
                commands.append(self.commands.get_nowait())
            except queue.Empty:
                break
        return commands

    def status(self) -> dict[str, Any]:
        status = self.transport.status()
        status.update({
            "reader_running": self.running,
            "queued_commands": self.commands.qsize(),
            "last_error": self.last_error,
        })
        return status


class PhoneUsbOutbox:
    """Persist results until a Galaxy app opens the USB CDC interface."""

    def __init__(
        self,
        root: Path,
        *,
        transport: RouterMonitorTransport,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.root = root
        self.outbox = root / "data" / "phone-outbox"
        self.results = root / "data" / "results"
        self.transport = transport
        self.timeout_seconds = timeout_seconds
        self.outbox.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _request_id(value: str) -> str:
        canonical = str(uuid.UUID(value))
        if canonical != value:
            raise PhoneUsbError("Phone outbox request ID is not canonical.")
        return canonical

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        temporary = path.with_suffix(path.suffix + ".partial")
        temporary.write_bytes(data)
        os.replace(temporary, path)

    def enqueue(
        self,
        request_id: str,
        media_type: str,
        metadata: dict[str, Any],
        payload: bytes,
    ) -> dict[str, Any]:
        canonical = self._request_id(request_id)
        frame = build_phone_frame(media_type, metadata, payload)
        self._atomic_write(self.outbox / f"{canonical}.lwr2", frame)
        return {
            "status": "queued",
            "protocol": "LWRX/2",
            "transport": self.transport.name,
            "frame_bytes": len(frame),
            "metadata_bytes": len(_canonical_metadata(metadata)),
            "media_bytes": len(payload),
        }

    def _record_delivery(
        self,
        request_id: str,
        receipt: dict[str, Any],
    ) -> None:
        result_path = self.results / f"{request_id}.json"
        if not result_path.is_file():
            return
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(result, dict):
            return
        result["phone_usb"] = receipt
        self._atomic_write(
            result_path,
            json.dumps(result, sort_keys=True, separators=(",", ":")).encode(),
        )

    def deliver_once(self) -> dict[str, Any] | None:
        candidates = sorted(self.outbox.glob("*.lwr2"))
        if not candidates:
            return None
        frame_path = candidates[0]
        request_id = self._request_id(frame_path.stem)
        frame = frame_path.read_bytes()
        parsed = parse_phone_frame(frame)
        started = time.perf_counter()
        written = self.transport.write(frame, self.timeout_seconds)
        elapsed = time.perf_counter() - started
        receipt = {
            "status": "sent",
            "protocol": "LWRX/2",
            "transport": self.transport.name,
            "request_id": request_id,
            "media_type": parsed.media_type,
            "frame_bytes": len(frame),
            "media_bytes": len(parsed.payload),
            "written_bytes": written,
            "crc32": f"{parsed.crc32:08x}",
            "send_seconds": elapsed,
        }
        frame_path.unlink()
        self._record_delivery(request_id, receipt)
        return receipt

    def send_status(self, value: dict[str, Any]) -> dict[str, Any]:
        """Send an ephemeral receiver-state frame while Android is connected."""

        metadata = {
            "content_type": CONTENT_TYPES["status"],
            "protocol": "LWRX/2",
            "receiver": "LightWeave Receiver",
        }
        payload = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        frame = build_phone_frame("status", metadata, payload)
        started = time.perf_counter()
        written = self.transport.write(frame, min(self.timeout_seconds, 1.0))
        return {
            "status": "sent",
            "protocol": "LWRX/2",
            "media_type": "status",
            "frame_bytes": len(frame),
            "written_bytes": written,
            "send_seconds": time.perf_counter() - started,
        }

    def status(self) -> dict[str, Any]:
        status = self.transport.status()
        status.update({
            "protocol": "LWRX/2",
            "queued_results": len(list(self.outbox.glob("*.lwr2"))),
        })
        return status
