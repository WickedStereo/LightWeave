"""USB/ADB transport for the UNO Q App Lab transmitter inbox."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .optical_frame import (
    FRAME_OVERHEAD_BYTES,
    build_header,
    crc16_ccitt_false,
    profile_for_preset,
)
from .raw import (
    RAW_AUDIO_CHUNK_BYTES,
    parse_raw_audio_preset,
    parse_raw_image_preset,
)
from .transport import SendReceipt

TRANSMITTER_PATH = "/home/arduino/ArduinoApps/lightweave_transmitter"
MAX_PAYLOAD_BYTES = 2_048
MAX_AUDIO_BYTES = 940
SAMPLES_PER_AUDIO_CHUNK = 24_000
RESULT_TIMEOUT_SECONDS = 240.0
REQUEST_SCHEMA_VERSION = 2
REQUEST_ID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)


class UnoQTransportError(RuntimeError):
    """The dashboard could not safely submit a payload to UNO Q."""


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _run_default(
    command: Sequence[str], **kwargs: object
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, **kwargs)  # noqa: S603


def resolve_adb_path(explicit: str | Path | None = None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    if configured := os.environ.get("LIGHTWEAVE_ADB_PATH"):
        candidates.append(Path(configured))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.extend(
            [
                Path(local) / "Android" / "Sdk" / "platform-tools" / "adb.exe",
                Path(local)
                / "Arduino15"
                / "packages"
                / "arduino"
                / "tools"
                / "adb"
                / "32.0.0"
                / "adb.exe",
            ]
        )
    if discovered := shutil.which("adb"):
        candidates.append(Path(discovered))
    for path in candidates:
        if path.is_file():
            return path.resolve()
    raise UnoQTransportError(
        "ADB was not found. Install Android platform-tools or set "
        "LIGHTWEAVE_ADB_PATH."
    )


def validate_uno_q_payload(payload: bytes, media_type: str, preset_code: str) -> None:
    if not payload:
        raise UnoQTransportError("Payload is empty.")
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise UnoQTransportError("Payload exceeds the 2,048-byte transmitter buffer.")
    if media_type == "image":
        try:
            preset = parse_raw_image_preset(preset_code)
        except ValueError as exc:
            raise UnoQTransportError(str(exc)) from exc
        if len(payload) > preset.maximum_bytes:
            raise UnoQTransportError(
                f"Raw image exceeds the {preset.maximum_bytes}-byte preset budget."
            )
        return
    if media_type != "audio":
        raise UnoQTransportError("Media type must be image or audio.")
    try:
        samples = parse_raw_audio_preset(preset_code)
    except ValueError as exc:
        raise UnoQTransportError(str(exc)) from exc
    if len(payload) > MAX_AUDIO_BYTES:
        raise UnoQTransportError("Raw audio exceeds the five-second/940-byte limit.")
    if len(payload) % RAW_AUDIO_CHUNK_BYTES:
        raise UnoQTransportError("Raw audio size must be divisible by 188 bytes.")
    chunks = len(payload) // RAW_AUDIO_CHUNK_BYTES
    minimum = (chunks - 1) * SAMPLES_PER_AUDIO_CHUNK + 1
    maximum = chunks * SAMPLES_PER_AUDIO_CHUNK
    if not minimum <= samples <= maximum:
        raise UnoQTransportError(
            "Audio sample count is impossible for the payload size."
        )
    for offset in range(0, len(payload), RAW_AUDIO_CHUNK_BYTES):
        if payload[offset + RAW_AUDIO_CHUNK_BYTES - 1] & 0xF0:
            raise UnoQTransportError("Raw audio chunk has non-zero padding bits.")


class UnoQAdbSink:
    """Publish one message to the transmitter app's atomic USB inbox."""

    def __init__(
        self,
        *,
        media_type: str,
        preset_code: str,
        adb_path: str | Path | None = None,
        device_serial: str | None = None,
        runner: Runner = _run_default,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        timeout_seconds: float = RESULT_TIMEOUT_SECONDS,
        wire_mode: str = "lwf1",
    ) -> None:
        self.media_type = media_type
        self.preset_code = preset_code
        self.adb_path = resolve_adb_path(adb_path)
        self.device_serial = device_serial or os.environ.get(
            "LIGHTWEAVE_UNO_Q_SERIAL"
        )
        self.runner = runner
        self.sleep = sleep
        self.clock = clock
        self.timeout_seconds = timeout_seconds
        if wire_mode not in {"lwf1", "raw-v0"}:
            raise UnoQTransportError("Wire mode must be lwf1 or raw-v0.")
        self.wire_mode = wire_mode

    def _run(self, arguments: Sequence[str], *, check: bool = True) -> str:
        completed = self.runner(
            [str(self.adb_path), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        if check and completed.returncode != 0:
            message = (
                completed.stderr or completed.stdout or "ADB command failed."
            ).strip()
            raise UnoQTransportError(message)
        return completed.stdout

    def _select_device(self) -> str:
        lines = self._run(["devices", "-l"]).splitlines()[1:]
        connected: dict[str, str] = {}
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                connected[parts[0]] = parts[1]
        if self.device_serial:
            state = connected.get(self.device_serial)
            if state != "device":
                raise UnoQTransportError(
                    "The configured UNO Q is not connected or authorized."
                )
            return self.device_serial
        ready = [serial for serial, state in connected.items() if state == "device"]
        uno_devices: list[str] = []
        for serial in ready:
            probe = self.runner(
                [
                    str(self.adb_path),
                    "-s",
                    serial,
                    "shell",
                    "arduino-app-cli",
                    "version",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            if probe.returncode == 0 and "Arduino App CLI version" in probe.stdout:
                uno_devices.append(serial)
        if len(uno_devices) == 1:
            return uno_devices[0]
        transmitter_devices: list[str] = []
        for serial in uno_devices:
            marker = self.runner(
                [
                    str(self.adb_path),
                    "-s",
                    serial,
                    "shell",
                    "test",
                    "-f",
                    f"{TRANSMITTER_PATH}/transmitter.manifest.json",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            if marker.returncode != 0:
                continue
            app_list = self.runner(
                [
                    str(self.adb_path),
                    "-s",
                    serial,
                    "shell",
                    "arduino-app-cli",
                    "--format",
                    "json",
                    "app",
                    "list",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            if app_list.returncode:
                continue
            try:
                applications = json.loads(app_list.stdout)["apps"]
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
            if any(
                entry.get("name") == "lightweave_transmitter"
                and entry.get("status") == "running"
                for entry in applications
            ):
                transmitter_devices.append(serial)
        if len(transmitter_devices) != 1:
            raise UnoQTransportError(
                "Could not uniquely identify a running lightweave_transmitter; "
                "configure LIGHTWEAVE_UNO_Q_SERIAL to resolve the ambiguity."
            )
        return transmitter_devices[0]

    def _device(
        self, serial: str, arguments: Sequence[str], *, check: bool = True
    ) -> str:
        return self._run(["-s", serial, *arguments], check=check)

    def status(self) -> dict[str, object]:
        serial = self._select_device()
        architecture = self._device(serial, ["shell", "uname", "-m"]).strip()
        if architecture != "aarch64":
            raise UnoQTransportError(
                "Connected ADB device is not an ARM64 UNO Q target."
            )
        output = self._device(
            serial,
            ["shell", "arduino-app-cli", "--format", "json", "app", "list"],
        )
        try:
            applications = json.loads(output)["apps"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise UnoQTransportError(
                "Arduino App CLI returned malformed status."
            ) from exc
        app = next(
            (
                entry
                for entry in applications
                if entry.get("name") == "lightweave_transmitter"
            ),
            None,
        )
        if app is None:
            return {
                "connected": True,
                "ready": False,
                "device": "Arduino UNO Q",
                "transport": "usb-adb-inbox",
                "app_status": "not-installed",
                "maximum_payload_bytes": MAX_PAYLOAD_BYTES,
            }
        marker_status = self.runner(
            [
                str(self.adb_path),
                "-s",
                serial,
                "shell",
                "test",
                "-f",
                f"{TRANSMITTER_PATH}/transmitter.manifest.json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        ready = app.get("status") == "running" and marker_status.returncode == 0
        busy_remaining = 0.0
        active_request: str | None = None
        if ready:
            state_result = self.runner(
                [
                    str(self.adb_path),
                    "-s",
                    serial,
                    "exec-out",
                    "cat",
                    f"{TRANSMITTER_PATH}/data/transmitter-state.json",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            if state_result.returncode == 0 and state_result.stdout.strip():
                try:
                    state = json.loads(state_result.stdout)
                    busy_remaining = max(
                        0.0, float(state.get("busy_until_epoch", 0.0)) - time.time()
                    )
                    if busy_remaining:
                        active_request = str(state.get("request_id") or "") or None
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
        return {
            "connected": True,
            "ready": ready,
            "device": "Arduino UNO Q",
            "transport": "usb-adb-inbox",
            "app_status": app.get("status", "unknown"),
            "maximum_payload_bytes": MAX_PAYLOAD_BYTES,
            "default_wire_mode": "lwf1",
            "frame_overhead_bytes": FRAME_OVERHEAD_BYTES,
            "busy": busy_remaining > 0,
            "busy_remaining_seconds": busy_remaining,
            "active_request": active_request is not None,
        }

    def _remote(self, serial: str, command: str) -> str:
        return self._device(serial, ["shell", command])

    def send(self, payload: bytes) -> SendReceipt:
        value = bytes(payload)
        validate_uno_q_payload(value, self.media_type, self.preset_code)
        serial = self._select_device()
        status = self.status()
        if not status["ready"]:
            raise UnoQTransportError(
                "lightweave_transmitter is not installed and running; run the "
                "UNO Q transmitter installer first."
            )

        request_id = str(uuid.uuid4())
        if REQUEST_ID.fullmatch(request_id) is None:  # pragma: no cover
            raise UnoQTransportError("Could not create a safe request ID.")
        digest = hashlib.sha256(value).hexdigest()
        profile, media_parameter = profile_for_preset(self.preset_code)
        header = build_header(self.preset_code, len(value))
        crc = crc16_ccitt_false(header + value)
        metadata = {
            "schema_version": REQUEST_SCHEMA_VERSION,
            "request_id": request_id,
            "media_type": self.media_type,
            "preset_code": self.preset_code,
            "payload_bytes": len(value),
            "payload_sha256": digest,
            "wire_mode": self.wire_mode,
            "frame_version": 1 if self.wire_mode == "lwf1" else 0,
            "profile_id": profile.profile_id,
            "media_parameter": media_parameter,
            "expected_header_hex": header.hex() if self.wire_mode == "lwf1" else "",
            "expected_crc16": crc if self.wire_mode == "lwf1" else None,
        }
        inbox = f"{TRANSMITTER_PATH}/data/inbox"
        results = f"{TRANSMITTER_PATH}/data/results"
        payload_partial = f"{inbox}/{request_id}.bin.partial"
        payload_final = f"{inbox}/{request_id}.bin"
        request_partial = f"{inbox}/{request_id}.json.partial"
        request_final = f"{inbox}/{request_id}.json"
        result_path = f"{results}/{request_id}.json"

        self._remote(serial, f"mkdir -p '{inbox}' '{results}'")
        with tempfile.TemporaryDirectory(prefix="lightweave-uno-tx-") as temporary:
            local_payload = Path(temporary) / "payload.bin"
            local_request = Path(temporary) / "request.json"
            local_payload.write_bytes(value)
            local_request.write_text(
                json.dumps(metadata, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            self._device(serial, ["push", str(local_payload), payload_partial])
            self._device(serial, ["push", str(local_request), request_partial])
        self._remote(serial, f"mv '{payload_partial}' '{payload_final}'")
        self._remote(serial, f"mv '{request_partial}' '{request_final}'")

        deadline = self.clock() + self.timeout_seconds
        result: Mapping[str, Any] | None = None
        while self.clock() < deadline:
            available = self.runner(
                [
                    str(self.adb_path),
                    "-s",
                    serial,
                    "shell",
                    "test",
                    "-s",
                    result_path,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            if available.returncode != 0:
                self.sleep(0.2)
                continue
            completed = self.runner(
                [str(self.adb_path), "-s", serial, "exec-out", "cat", result_path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            if completed.returncode == 0 and completed.stdout.strip():
                try:
                    parsed = json.loads(completed.stdout)
                except json.JSONDecodeError as exc:
                    raise UnoQTransportError(
                        "UNO Q returned malformed transmission evidence."
                    ) from exc
                if (
                    not isinstance(parsed, dict)
                    or parsed.get("request_id") != request_id
                ):
                    raise UnoQTransportError(
                        "UNO Q returned mismatched transmission evidence."
                    )
                result = parsed
                break
            self.sleep(0.2)
        if result is None:
            raise UnoQTransportError(
                "Timed out while UNO Q was buffering the payload. The request may "
                "still complete; inspect App Lab logs before retrying."
            )
        self._remote(serial, f"rm -f '{result_path}'")
        if not result.get("accepted"):
            raise UnoQTransportError(
                str(result.get("error", "UNO Q rejected the payload."))
            )
        if (
            result.get("schema_version") != REQUEST_SCHEMA_VERSION
            or result.get("payload_sha256") != digest
            or result.get("buffered_bytes") != len(value)
            or result.get("wire_mode") != self.wire_mode
        ):
            raise UnoQTransportError(
                "UNO Q acceptance evidence does not match the request schema or "
                "payload."
            )
        return SendReceipt(len(value), "uno-q-app-lab-adb", result)
