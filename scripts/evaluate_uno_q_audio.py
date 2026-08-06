"""Compare native UNO Q audio intermediates/output with pinned PyTorch."""

from __future__ import annotations

import argparse
import json
import math
import sys
import wave
from pathlib import Path

import numpy as np
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightweave.audio import condition_chunk_boundaries, load_audio_model  # noqa: E402
from lightweave.raw import (  # noqa: E402
    parse_raw_audio_preset,
    unpack_raw_audio_chunks,
)


def read_pcm16(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as stream:
        if (
            stream.getnchannels() != 1
            or stream.getsampwidth() != 2
            or stream.getframerate() != 24_000
            or stream.getcomptype() != "NONE"
        ):
            raise RuntimeError("Board WAV is not 24 kHz mono PCM16.")
        frames = stream.readframes(stream.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32767.0


def quality(reference: np.ndarray, actual: np.ndarray) -> dict[str, float]:
    if reference.shape != actual.shape or not np.isfinite(actual).all():
        raise RuntimeError("Board output shape/finite validation failed.")
    difference = reference.astype(np.float64) - actual.astype(np.float64)
    mse = float(np.mean(np.square(difference)))
    peak = max(1.0, float(np.max(np.abs(reference))))
    psnr = 300.0 if mse == 0 else 10 * math.log10(peak * peak / mse)
    return {
        "psnr_db": psnr,
        "maximum_absolute_error": float(np.max(np.abs(difference))),
        "mean_absolute_error": float(np.mean(np.abs(difference))),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--preset", required=True)
    parser.add_argument("--board-wav", type=Path, required=True)
    parser.add_argument("--native-embedding", type=Path)
    parser.add_argument("--native-codes", type=Path)
    parser.add_argument("--weights", type=Path)
    parser.add_argument("--split", type=int, default=5)
    args = parser.parse_args()

    original_samples = parse_raw_audio_preset(args.preset)
    payload = args.payload.read_bytes()
    codes = unpack_raw_audio_chunks(payload)
    model, _, fingerprint = load_audio_model(args.weights)
    with torch.inference_mode():
        embedding = model.quantizer.decode(codes.transpose(0, 1))
        prefix = model.decoder.model[: args.split](embedding)
        chunk_count = len(payload) // 188
        if prefix.shape[-1] % chunk_count:
            raise RuntimeError("CPU prefix cannot be divided into audio chunks.")
        prefix_frames = prefix.shape[-1] // chunk_count
        reconstructed = torch.cat(
            [
                model.decoder.model[args.split :](
                    prefix[..., index * prefix_frames : (index + 1) * prefix_frames]
                )
                for index in range(chunk_count)
            ],
            dim=-1,
        )
        reference = condition_chunk_boundaries(reconstructed)[..., :original_samples]
    reference_array = reference.detach().cpu().numpy().reshape(-1)
    board_array = read_pcm16(args.board_wav)
    output_parity = quality(reference_array, board_array)
    result: dict[str, object] = {
        "status": "ok",
        "preset_code": args.preset,
        "payload_bytes": len(payload),
        "output_samples": int(board_array.size),
        "selected_split": args.split,
        "model_sha256": fingerprint.hex(),
        "output_parity": output_parity,
    }

    if args.native_codes:
        native_codes = np.frombuffer(args.native_codes.read_bytes(), dtype="<u2")
        expected_codes = codes.squeeze(0).transpose(0, 1).reshape(-1).cpu().numpy()
        result["native_code_indices_exact"] = bool(
            np.array_equal(native_codes, expected_codes)
        )
        if not result["native_code_indices_exact"]:
            raise RuntimeError("Native 10-bit code indices differ from Python.")

    if args.native_embedding:
        native_embedding = np.load(args.native_embedding).reshape(embedding.shape)
        difference = np.abs(native_embedding - embedding.detach().cpu().numpy())
        maximum = float(difference.max())
        result["native_codebook_maximum_absolute_error"] = maximum
        if maximum > 1e-6:
            raise RuntimeError("Native codebook reconstruction exceeds 1e-6.")

    if output_parity["psnr_db"] < 35.0:
        raise RuntimeError("UNO Q output parity is below 35 dB.")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        raise SystemExit(2) from error
