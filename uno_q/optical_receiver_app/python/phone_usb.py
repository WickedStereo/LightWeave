"""Durable decoded-result delivery over the UNO Q USB CDC gadget."""

from __future__ import annotations

import errno
import json
import os
import queue
import select
import struct
import threading
import time
import uuid
import zlib
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import termios
    import tty
except ModuleNotFoundError:  # Protocol and outbox tests also run on Windows.
    termios = None  # type: ignore[assignment]
    tty = None  # type: ignore[assignment]

TERMINAL_ERRORS = (OSError,) if termios is None else (OSError, termios.error)

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
    """Receive controls on a blocking worker so gadget bytes are never missed."""

    def __init__(self, device: Path = Path("/dev/ttyGS0")) -> None:
        self.device = device
        self.descriptor: int | None = None
        self.original_attributes: list[Any] | None = None
        self.buffer = bytearray()
        self.last_error: str | None = None
        self.commands: queue.Queue[str] = queue.Queue()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.lock = threading.Lock()

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

    def _close_descriptor(self) -> None:
        with self.lock:
            descriptor = self.descriptor
            attributes = self.original_attributes
            self.descriptor = None
            self.original_attributes = None
        if descriptor is None:
            return
        if attributes is not None and termios is not None:
            with suppress(termios.error):
                termios.tcsetattr(descriptor, termios.TCSANOW, attributes)
        with suppress(OSError):
            os.close(descriptor)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                descriptor = os.open(self.device, os.O_RDONLY | os.O_NOCTTY)
                attributes = None
                try:
                    if termios is None or tty is None:
                        raise OSError("POSIX terminal control is unavailable.")
                    attributes = termios.tcgetattr(descriptor)
                    tty.setraw(descriptor, when=termios.TCSANOW)
                except TERMINAL_ERRORS:
                    attributes = None
                with self.lock:
                    self.descriptor = descriptor
                    self.original_attributes = attributes
                self.last_error = None
                while not self.stop_event.is_set():
                    data = os.read(descriptor, 4096)
                    if not data:
                        break
                    print(
                        f"Phone USB received {len(data)} control bytes",
                        flush=True,
                    )
                    self._accept(data)
            except OSError as exc:
                if not self.stop_event.is_set():
                    self.last_error = str(exc)
            finally:
                self._close_descriptor()
            self.stop_event.wait(0.1)

    def start(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run,
            name="lightweave-phone-usb",
            daemon=True,
        )
        self.thread.start()

    def close(self) -> None:
        self.stop_event.set()
        self._close_descriptor()
        if self.thread is not None:
            self.thread.join(timeout=1.0)
        self.thread = None

    def poll(self) -> list[str]:
        self.start()
        commands: list[str] = []
        while True:
            try:
                commands.append(self.commands.get_nowait())
            except queue.Empty:
                break
        return commands

    def status(self) -> dict[str, Any]:
        return {
            "device": str(self.device),
            "reader_open": self.descriptor is not None,
            "reader_running": self.thread is not None and self.thread.is_alive(),
            "queued_commands": self.commands.qsize(),
            "last_error": self.last_error,
        }


def _write_all(device: Path, data: bytes, timeout_seconds: float) -> int:
    deadline = time.monotonic() + timeout_seconds
    try:
        descriptor = os.open(device, os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK)
    except OSError as exc:
        if exc.errno in {
            errno.EACCES,
            errno.EAGAIN,
            errno.EBUSY,
            errno.ENODEV,
            errno.ENXIO,
            errno.EPERM,
        }:
            raise PhoneUsbUnavailable(
                "Galaxy USB receiver is not connected or has not opened CDC."
            ) from exc
        raise PhoneUsbError(f"Could not open phone USB endpoint: {exc}.") from exc
    original_attributes = None
    try:
        try:
            if termios is None or tty is None:
                raise OSError("POSIX terminal control is unavailable.")
            original_attributes = termios.tcgetattr(descriptor)
            tty.setraw(descriptor, when=termios.TCSANOW)
        except TERMINAL_ERRORS:
            original_attributes = None
        view = memoryview(data)
        written = 0
        while written < len(data):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PhoneUsbUnavailable("Galaxy USB write timed out.")
            _, writable, _ = select.select([], [descriptor], [], remaining)
            if not writable:
                raise PhoneUsbUnavailable("Galaxy USB write timed out.")
            try:
                count = os.write(descriptor, view[written:])
            except BlockingIOError:
                continue
            if count <= 0:
                raise PhoneUsbUnavailable("Galaxy USB endpoint stopped accepting data.")
            written += count
        if termios is not None:
            termios.tcdrain(descriptor)
        return written
    except OSError as exc:
        if exc.errno in {errno.EAGAIN, errno.EIO, errno.ENODEV, errno.ENXIO}:
            raise PhoneUsbUnavailable("Galaxy USB connection was interrupted.") from exc
        raise PhoneUsbError(f"Galaxy USB write failed: {exc}.") from exc
    finally:
        if original_attributes is not None and termios is not None:
            with suppress(termios.error):
                termios.tcsetattr(
                    descriptor,
                    termios.TCSANOW,
                    original_attributes,
                )
        os.close(descriptor)


class PhoneUsbOutbox:
    """Persist results until a Galaxy app opens the USB CDC interface."""

    def __init__(
        self,
        root: Path,
        *,
        device: Path = Path("/dev/ttyGS0"),
        timeout_seconds: float = 5.0,
    ) -> None:
        self.root = root
        self.outbox = root / "data" / "phone-outbox"
        self.results = root / "data" / "results"
        self.device = device
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
            "device": str(self.device),
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
        written = _write_all(self.device, frame, self.timeout_seconds)
        elapsed = time.perf_counter() - started
        receipt = {
            "status": "sent",
            "protocol": "LWRX/2",
            "device": str(self.device),
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
        written = _write_all(self.device, frame, min(self.timeout_seconds, 1.0))
        return {
            "status": "sent",
            "protocol": "LWRX/2",
            "media_type": "status",
            "frame_bytes": len(frame),
            "written_bytes": written,
            "send_seconds": time.perf_counter() - started,
        }

    def status(self) -> dict[str, Any]:
        return {
            "protocol": "LWRX/2",
            "device": str(self.device),
            "device_present": self.device.exists(),
            "device_writable": os.access(self.device, os.W_OK),
            "queued_results": len(list(self.outbox.glob("*.lwr2"))),
        }
