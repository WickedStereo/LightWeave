"""Arm the UNO Q byte receiver, transmit a short pattern, and compare bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
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

RECEIVER_PATH = "/home/arduino/ArduinoApps/lightweave_byte_receiver"


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transmitter-serial", required=True)
    parser.add_argument("--receiver-serial", required=True)
    parser.add_argument("--payload-hex", default="00ffaa55")
    parser.add_argument("--adb-path")
    args = parser.parse_args()

    try:
        payload = bytes.fromhex(args.payload_hex)
    except ValueError as exc:
        raise SystemExit(f"Invalid --payload-hex: {exc}") from exc
    if not 1 <= len(payload) <= 128:
        raise SystemExit("Verification payload must contain 1-128 bytes.")

    adb = resolve_adb_path(args.adb_path)
    request_id = str(uuid.uuid4())
    inbox = f"{RECEIVER_PATH}/data/inbox"
    state_path = f"{RECEIVER_PATH}/data/receiver-state.json"
    result_json = f"{RECEIVER_PATH}/data/results/{request_id}.json"
    result_bin = f"{RECEIVER_PATH}/data/results/{request_id}.bin"
    descriptor = {
        "schema_version": 1,
        "request_id": request_id,
        "expected_bytes": len(payload),
    }
    with tempfile.TemporaryDirectory(prefix="lightweave-byte-rx-") as temporary:
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
        preset_code="I64-Q1-B128",
        adb_path=adb,
        device_serial=args.transmitter_serial,
    ).send(payload)
    timeout = max(20.0, (len(payload) * 8 + 2) * 0.025 + 10.0)
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
    received = run_adb(adb, args.receiver_serial, ["exec-out", "cat", result_bin])
    exact = received == payload
    report = {
        "request_id": request_id,
        "transmitter_serial": args.transmitter_serial,
        "receiver_serial": args.receiver_serial,
        "sent_hex": payload.hex(),
        "received_hex": received.hex(),
        "sent_bytes": len(payload),
        "received_bytes": len(received),
        "sent_sha256": hashlib.sha256(payload).hexdigest(),
        "received_sha256": hashlib.sha256(received).hexdigest(),
        "exact_match": exact,
        "stop_bit_valid": bool(result.get("stop_bit_valid")),
        "transmitter": send_receipt.evidence,
        "receiver": result,
    }
    print(json.dumps(report, indent=2))
    return 0 if exact and report["stop_bit_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
