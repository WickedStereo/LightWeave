"""Send one raw audio payload through LWF1 and verify UNO Q reconstruction."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
import uuid
import wave
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightweave.uno_q_transport import UnoQAdbSink, resolve_adb_path  # noqa: E402

RECEIVER_PATH = "/home/arduino/ArduinoApps/lightweave_optical_receiver"
AUDIO_PRESET = re.compile(r"A1-E15-S([1-9][0-9]*)")


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
    parser.add_argument("payload", type=Path)
    parser.add_argument("--preset", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--transmitter-serial", required=True)
    parser.add_argument("--receiver-serial", required=True)
    parser.add_argument("--adb-path")
    args = parser.parse_args()

    match = AUDIO_PRESET.fullmatch(args.preset)
    if match is None:
        raise SystemExit("--preset must use A1-E15-S<n>.")
    samples = int(match.group(1))
    payload = args.payload.read_bytes()
    if not 1 <= len(payload) <= 940 or len(payload) % 188:
        raise SystemExit("Audio payload must contain 1-940 bytes in 188-byte chunks.")

    adb = resolve_adb_path(args.adb_path)
    request_id = str(uuid.uuid4())
    inbox = f"{RECEIVER_PATH}/data/inbox"
    state_path = f"{RECEIVER_PATH}/data/receiver-state.json"
    result_json = f"{RECEIVER_PATH}/data/results/{request_id}.json"
    result_wav = f"{RECEIVER_PATH}/data/results/{request_id}.wav"
    descriptor = {
        "schema_version": 2,
        "request_id": request_id,
        "action": "listen-lwf1",
    }
    with tempfile.TemporaryDirectory(prefix="lightweave-optical-audio-") as temporary:
        local = Path(temporary) / "listen.json"
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
    send_receipt = UnoQAdbSink(
        media_type="audio",
        preset_code=args.preset,
        adb_path=adb,
        device_serial=args.transmitter_serial,
    ).send(payload)
    timeout = max(180.0, ((len(payload) + 12) * 8 + 2) * 0.025 + 180.0)
    result = wait_for_status(
        adb,
        args.receiver_serial,
        result_json,
        request_id,
        {"completed", "error"},
        timeout,
    )
    if not result.get("accepted"):
        raise RuntimeError(str(result.get("error", "Receiver rejected the frame.")))

    wav_data = run_adb(adb, args.receiver_serial, ["exec-out", "cat", result_wav])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = args.output.with_suffix(args.output.suffix + ".partial")
    temporary_output.write_bytes(wav_data)
    temporary_output.replace(args.output)
    with wave.open(str(args.output), "rb") as stream:
        wav_contract = (
            stream.getnchannels() == 1
            and stream.getsampwidth() == 2
            and stream.getframerate() == 24_000
            and stream.getnframes() == samples
        )
    reconstruction = result.get("reconstruction", {})
    passed = all(
        (
            result.get("payload_sha256") == hashlib.sha256(payload).hexdigest(),
            result.get("received_bytes") == len(payload),
            result.get("media_parameter") == samples,
            result.get("crc_valid") is True,
            result.get("stop_bit_valid") is True,
            reconstruction.get("backend") == "ncnn-hybrid-cpu-vulkan",
            reconstruction.get("strict_suffix_no_fallback") is True,
            reconstruction.get("vulkan_compute_layers") == 39,
            "Adreno" in str(reconstruction.get("device", "")),
            wav_contract,
        )
    )
    report = {
        "status": "ok" if passed else "failed",
        "request_id": request_id,
        "preset_code": args.preset,
        "payload_bytes": len(payload),
        "output": str(args.output.resolve()),
        "output_samples": samples,
        "transmitter": send_receipt.evidence,
        "receiver": result,
    }
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
