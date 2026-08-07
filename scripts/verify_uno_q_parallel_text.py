"""Verify exact text framing across the three-lane UNO Q sketch pair."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightweave.optical_frame import build_frame, crc16_ccitt_false  # noqa: E402
from lightweave.text import TEXT_PRESET_CODE, encode_text  # noqa: E402
from lightweave.uno_q_transport import resolve_adb_path  # noqa: E402

TRANSMITTER_CONTAINER = "lightweave_parallel_transmitter-main-1"
RECEIVER_CONTAINER = "lightweave_parallel_receiver-main-1"


def run_bridge_python(
    adb: Path,
    serial: str,
    container: str,
    source: str,
    *,
    timeout: float = 30.0,
) -> str:
    completed = subprocess.run(  # noqa: S603
        [
            str(adb),
            "-s",
            serial,
            "shell",
            "docker",
            "exec",
            "-i",
            container,
            "python",
            "-",
        ],
        input=source.encode("utf-8"),
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode:
        message = (completed.stderr or completed.stdout).decode(
            "utf-8", errors="replace"
        )
        raise RuntimeError(message.strip() or "UNO Q Bridge command failed.")
    return completed.stdout.decode("utf-8", errors="strict").strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", default="3-LANE")
    parser.add_argument("--transmitter-serial", required=True)
    parser.add_argument("--receiver-serial", required=True)
    parser.add_argument("--adb-path")
    args = parser.parse_args()

    payload = encode_text(args.text)
    frame = build_frame(payload, TEXT_PRESET_CODE)
    expected_crc = crc16_ccitt_false(frame[:-2])
    adb = resolve_adb_path(args.adb_path)

    armed = run_bridge_python(
        adb,
        args.receiver_serial,
        RECEIVER_CONTAINER,
        """
from arduino.app_utils import Bridge
Bridge.call("reset_receiver", timeout=2)
print(Bridge.call("start_listen", timeout=2))
""",
    )
    if armed != "True":
        raise RuntimeError(f"Parallel receiver refused to listen: {armed}")

    payload_values = list(payload)
    transmitted = run_bridge_python(
        adb,
        args.transmitter_serial,
        TRANSMITTER_CONTAINER,
        f"""
from arduino.app_utils import Bridge
payload = bytes({payload_values!r})
assert Bridge.call("prepare_transmission", len(payload), 1, 0x20, 0, timeout=3)
for index, value in enumerate(payload):
    assert Bridge.call("store_image_byte", index, value, timeout=3)
assert Bridge.call("get_loaded_byte_count", timeout=3) == len(payload)
print(Bridge.call("transmit_payload", timeout=30))
""",
        timeout=60.0,
    )
    if transmitted != "True":
        raise RuntimeError(f"Parallel transmitter rejected the frame: {transmitted}")

    time.sleep(0.75)
    evidence_text = run_bridge_python(
        adb,
        args.receiver_serial,
        RECEIVER_CONTAINER,
        """
import json
from arduino.app_utils import Bridge
count = int(Bridge.call("get_received_byte_count", timeout=2))
print(json.dumps({
    "payload_bytes": count,
    "payload_hex": (
        Bridge.call("get_received_chunk", 0, count, timeout=2)
        if count
        else ""
    ),
    "header_hex": Bridge.call("get_frame_header", timeout=2),
    "profile_id": int(Bridge.call("get_frame_profile_id", timeout=2)),
    "media_parameter": int(Bridge.call("get_media_parameter", timeout=2)),
    "received_crc": int(Bridge.call("get_received_crc", timeout=2)),
    "computed_crc": int(Bridge.call("get_computed_crc", timeout=2)),
    "stop_bit_valid": bool(Bridge.call("get_stop_bit_valid", timeout=2)),
    "error": Bridge.call("get_receiver_error_code", timeout=2),
}, sort_keys=True))
""",
    )
    evidence = json.loads(evidence_text)
    received = bytes.fromhex(evidence["payload_hex"])
    slots = (len(frame) + 2) // 3
    expected_header = frame[:10].hex().upper()
    passed = all(
        (
            received == payload,
            evidence["payload_bytes"] == len(payload),
            evidence["header_hex"] == expected_header,
            evidence["profile_id"] == 0x20,
            evidence["media_parameter"] == 0,
            evidence["received_crc"] == expected_crc,
            evidence["computed_crc"] == expected_crc,
            evidence["stop_bit_valid"] is True,
            evidence["error"] == "none",
        )
    )
    result = {
        "status": "ok" if passed else "failed",
        "text": received.decode("ascii") if received else "",
        "payload_bytes": len(payload),
        "frame_bytes": len(frame),
        "parallel_byte_slots": slots,
        "parallel_seconds": (slots * 8 + 2) * 0.025,
        "single_lane_seconds": (len(frame) * 8 + 2) * 0.025,
        "receiver": evidence,
    }
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
