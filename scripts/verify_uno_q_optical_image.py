"""Send one raw image payload through light and verify UNO Q reconstruction."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightweave.uno_q_transport import UnoQAdbSink, resolve_adb_path  # noqa: E402

RECEIVER_PATH = "/home/arduino/ArduinoApps/lightweave_optical_receiver"
PRESETS = {
    "I64-Q1-B128": (128, 64),
    "I128-Q1-B768": (768, 128),
    "I256-Q1-B2048": (2_048, 256),
}


def run_adb(adb: Path, serial: str, arguments: list[str]) -> bytes:
    completed = subprocess.run(  # noqa: S603
        [str(adb), "-s", serial, *arguments],
        capture_output=True,
        timeout=30,
        check=False,
    )
    if completed.returncode:
        message = (completed.stderr or completed.stdout).decode(
            "utf-8", errors="replace"
        )
        raise RuntimeError(message.strip() or "ADB command failed.")
    return completed.stdout


def read_json_if_present(adb: Path, serial: str, path: str) -> dict | None:
    exists = subprocess.run(  # noqa: S603
        [str(adb), "-s", serial, "shell", "test", "-s", path],
        capture_output=True,
        timeout=30,
        check=False,
    )
    if exists.returncode:
        return None
    raw = run_adb(adb, serial, ["exec-out", "cat", path])
    return json.loads(raw.decode("utf-8"))


def wait_for_status(
    adb: Path,
    serial: str,
    path: str,
    request_id: str,
    statuses: set[str],
    timeout: float,
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = read_json_if_present(adb, serial, path)
        if (
            value
            and value.get("request_id") == request_id
            and value.get("status") in statuses
        ):
            return value
        time.sleep(0.1)
    raise RuntimeError(f"Timed out waiting for receiver status: {sorted(statuses)}")


def png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("Receiver output is not a PNG image.")
    return struct.unpack(">II", data[16:24])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=Path)
    parser.add_argument("--preset", required=True, choices=tuple(PRESETS))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--transmitter-serial", required=True)
    parser.add_argument("--receiver-serial", required=True)
    parser.add_argument("--adb-path")
    args = parser.parse_args()

    payload = args.payload.read_bytes()
    maximum, output_size = PRESETS[args.preset]
    if not 1 <= len(payload) <= maximum:
        raise SystemExit(
            f"{args.preset} payload must contain 1-{maximum} bytes."
        )

    adb = resolve_adb_path(args.adb_path)
    request_id = str(uuid.uuid4())
    inbox = f"{RECEIVER_PATH}/data/inbox"
    state_path = f"{RECEIVER_PATH}/data/receiver-state.json"
    result_json = f"{RECEIVER_PATH}/data/results/{request_id}.json"
    result_png = f"{RECEIVER_PATH}/data/results/{request_id}.png"
    descriptor = {
        "schema_version": 1,
        "request_id": request_id,
        "media_type": "image",
        "preset_code": args.preset,
        "expected_bytes": len(payload),
    }
    with tempfile.TemporaryDirectory(prefix="lightweave-optical-image-") as temporary:
        local = Path(temporary) / "arm.json"
        local.write_text(json.dumps(descriptor), encoding="utf-8")
        partial = f"{inbox}/{request_id}.json.partial"
        run_adb(adb, args.receiver_serial, ["shell", "mkdir", "-p", inbox])
        run_adb(adb, args.receiver_serial, ["push", str(local), partial])
        run_adb(
            adb,
            args.receiver_serial,
            ["shell", "mv", partial, f"{inbox}/{request_id}.json"],
        )

    wait_for_status(
        adb,
        args.receiver_serial,
        state_path,
        request_id,
        {"armed"},
        15.0,
    )
    send_receipt = UnoQAdbSink(
        media_type="image",
        preset_code=args.preset,
        adb_path=adb,
        device_serial=args.transmitter_serial,
    ).send(payload)
    timeout = max(120.0, (len(payload) * 8 + 2) * 0.025 + 110.0)
    result = wait_for_status(
        adb,
        args.receiver_serial,
        result_json,
        request_id,
        {"completed", "error"},
        timeout,
    )
    if not result.get("accepted"):
        raise RuntimeError(str(result.get("error", "Receiver rejected the request.")))

    png = run_adb(adb, args.receiver_serial, ["exec-out", "cat", result_png])
    width, height = png_dimensions(png)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = args.output.with_suffix(args.output.suffix + ".partial")
    temporary_output.write_bytes(png)
    temporary_output.replace(args.output)
    expected_hash = hashlib.sha256(payload).hexdigest()
    reconstruction = result.get("reconstruction", {})
    passed = all(
        (
            result.get("payload_sha256") == expected_hash,
            result.get("received_bytes") == len(payload),
            result.get("stop_bit_valid") is True,
            (width, height) == (output_size, output_size),
            reconstruction.get("backend") == "ncnn-vulkan",
            reconstruction.get("strict_no_fallback") is True,
            "Adreno" in str(reconstruction.get("device", "")),
        )
    )
    report = {
        "status": "ok" if passed else "failed",
        "request_id": request_id,
        "transmitter_serial": args.transmitter_serial,
        "receiver_serial": args.receiver_serial,
        "preset_code": args.preset,
        "payload_bytes": len(payload),
        "payload_sha256": expected_hash,
        "stop_bit_valid": result.get("stop_bit_valid"),
        "output": str(args.output.resolve()),
        "output_dimensions": [width, height],
        "transmitter": send_receipt.evidence,
        "receiver": result,
    }
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

