"""Send printable ASCII through light and verify the UNO Q text receiver."""

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

from lightweave.text import TEXT_PRESET_CODE, encode_text  # noqa: E402
from lightweave.uno_q_transport import UnoQAdbSink, resolve_adb_path  # noqa: E402

RECEIVER_PATH = "/home/arduino/ArduinoApps/lightweave_receiver"


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
    return json.loads(run_adb(adb, serial, ["exec-out", "cat", path]))


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
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--transmitter-serial", required=True)
    parser.add_argument("--receiver-serial", required=True)
    parser.add_argument("--adb-path")
    args = parser.parse_args()

    payload = encode_text(args.text)
    adb = resolve_adb_path(args.adb_path)
    request_id = str(uuid.uuid4())
    inbox = f"{RECEIVER_PATH}/data/inbox"
    state_path = f"{RECEIVER_PATH}/data/receiver-state.json"
    result_json = f"{RECEIVER_PATH}/data/results/{request_id}.json"
    result_text = f"{RECEIVER_PATH}/data/results/{request_id}.txt"
    descriptor = {
        "schema_version": 2,
        "request_id": request_id,
        "action": "listen-lwf1",
    }
    with tempfile.TemporaryDirectory(prefix="lightweave-optical-text-") as temporary:
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
        adb, args.receiver_serial, state_path, request_id, {"listening"}, 15.0
    )
    receipt = UnoQAdbSink(
        media_type="text",
        preset_code=TEXT_PRESET_CODE,
        adb_path=adb,
        device_serial=args.transmitter_serial,
    ).send(payload)
    timeout = max(45.0, ((len(payload) + 12) * 8 + 2) * 0.025 + 20.0)
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

    received = run_adb(adb, args.receiver_serial, ["exec-out", "cat", result_text])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    partial_output = args.output.with_suffix(args.output.suffix + ".partial")
    partial_output.write_bytes(received)
    partial_output.replace(args.output)
    expected_hash = hashlib.sha256(payload).hexdigest()
    reconstruction = result.get("reconstruction", {})
    passed = all(
        (
            received == payload,
            result.get("payload_sha256") == expected_hash,
            result.get("profile_id") == 0x20,
            result.get("crc_valid") is True,
            result.get("stop_bit_valid") is True,
            reconstruction.get("accelerator_required") is False,
        )
    )
    print(
        json.dumps(
            {
                "status": "ok" if passed else "failed",
                "request_id": request_id,
                "preset_code": TEXT_PRESET_CODE,
                "text": received.decode("ascii"),
                "payload_bytes": len(payload),
                "output": str(args.output.resolve()),
                "transmitter": receipt.evidence,
                "receiver": result,
            },
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
