"""Run image and audio NPU loopbacks with non-loopback networking blocked."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightweave.audio import roundtrip_audio  # noqa: E402
from lightweave.image import write_bytes_atomic  # noqa: E402
from lightweave.offline import install_offline_guard  # noqa: E402
from lightweave.raw import (  # noqa: E402
    decode_raw_audio,
    decode_raw_image,
    encode_raw_audio,
    encode_raw_image,
)
from lightweave.service import roundtrip_image  # noqa: E402


def main() -> None:
    os.environ["LIGHTWEAVE_ENFORCE_OFFLINE"] = "1"
    install_offline_guard()
    output_dir = PROJECT_ROOT / "reports/generated/offline-smoke"
    output_dir.mkdir(parents=True, exist_ok=True)
    image = roundtrip_image(
        PROJECT_ROOT / "data/generated/demo-images/gradient-landscape.png",
        backend="qnn",
        payload_path=output_dir / "image.lwv",
        output_path=output_dir / "image.png",
    )
    audio = roundtrip_audio(
        PROJECT_ROOT / "data/generated/demo-audio/chirp-and-tones.wav",
        backend="hybrid-qnn",
        payload_path=output_dir / "audio.lwv",
        output_path=output_dir / "audio.wav",
    )
    raw_image_encoded = encode_raw_image(
        PROJECT_ROOT / "data/generated/demo-images/gradient-landscape.png"
    )
    write_bytes_atomic(raw_image_encoded.payload, output_dir / "raw-image.bin")
    raw_image = decode_raw_image(
        raw_image_encoded.payload,
        preset_code=raw_image_encoded.preset_code,
        backend="qnn",
        output_path=output_dir / "raw-image.png",
    )
    raw_audio_encoded = encode_raw_audio(
        PROJECT_ROOT / "data/generated/demo-audio/chirp-and-tones.wav"
    )
    write_bytes_atomic(raw_audio_encoded.payload, output_dir / "raw-audio.bin")
    raw_audio = decode_raw_audio(
        raw_audio_encoded.payload,
        preset_code=raw_audio_encoded.preset_code,
        backend="hybrid-qnn",
        output_path=output_dir / "raw-audio.wav",
    )
    report = {
        "offline_guard": "non-loopback networking blocked in all workers",
        "image": {
            "passed": image["npu_evidence"]["strict_no_fallback"],
            "envelope_bytes": image["envelope_bytes"],
        },
        "audio": {
            "passed": audio["execution_evidence"]["strict_no_fallback"],
            "envelope_bytes": audio["envelope_bytes"],
            "code_payload_bps": audio["code_payload_bps"],
        },
        "raw_image": {
            "passed": raw_image.evidence["strict_no_fallback"],
            "raw_bytes": len(raw_image_encoded.payload),
            "preset_code": raw_image_encoded.preset_code,
            "output_size": list(raw_image.image.size),
        },
        "raw_audio": {
            "passed": raw_audio.evidence["strict_no_fallback"],
            "raw_bytes": len(raw_audio_encoded.payload),
            "preset_code": raw_audio_encoded.preset_code,
            "restored_samples": int(raw_audio.waveform.shape[-1]),
        },
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
