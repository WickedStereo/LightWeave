"""Generate a deterministic two-second PCM WAV for audio acceptance tests."""

from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data/generated/demo-audio/chirp-and-tones.wav",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 24_000
    duration = 2.0
    time = np.arange(round(sample_rate * duration), dtype=np.float64) / sample_rate
    chirp_phase = 2 * np.pi * (180 * time + 0.5 * 420 * time**2)
    waveform = (
        0.42 * np.sin(chirp_phase)
        + 0.18 * np.sin(2 * np.pi * 880 * time)
        + 0.08 * np.sin(2 * np.pi * 1760 * time)
    )
    envelope = np.minimum(1.0, time * 8) * np.minimum(1.0, (duration - time) * 8)
    pcm = np.rint(np.clip(waveform * envelope, -0.999, 0.999) * 32767).astype(
        "<i2"
    )
    with wave.open(str(output), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(pcm.tobytes())
    print(output)


if __name__ == "__main__":
    main()
