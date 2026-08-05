"""Evaluate the EnCodec payload and strict CPU/QNN hybrid decoder."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightweave.audio import (  # noqa: E402
    condition_chunk_boundaries,
    cpu_prefix_chunks,
    cpu_tail_chunks,
    encode_audio,
    load_audio_model,
    maximum_boundary_jump,
    unpack_codes,
    write_wav_atomic,
)
from lightweave.audio_npu import reconstruct_audio_tail_on_npu  # noqa: E402
from lightweave.metrics import array_psnr  # noqa: E402


def evaluate(input_path: Path, output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    encoded = encode_audio(input_path)
    metadata = encoded.envelope.metadata
    model, _, _ = load_audio_model()
    codes = unpack_codes(encoded.envelope.payload, metadata.frame_count)
    with torch.inference_mode():
        embedding = model.quantizer.decode(codes.transpose(0, 1))
        cpu_full = model.decoder(embedding)[..., : metadata.original_samples]
    prefixes, cpu_prefix_seconds = cpu_prefix_chunks(embedding, model)
    cpu_tail = cpu_tail_chunks(prefixes, model)
    npu_started = time.perf_counter()
    npu_result = reconstruct_audio_tail_on_npu(
        prefixes, source_model_hash=metadata.model_sha256
    )
    npu_seconds = time.perf_counter() - npu_started
    raw_npu = torch.from_numpy(npu_result.output)
    tail_psnr = array_psnr(
        cpu_tail.detach().cpu().numpy(), raw_npu.detach().cpu().numpy()
    )
    raw_waveform = raw_npu.reshape(1, 1, -1)
    conditioned = condition_chunk_boundaries(raw_waveform)[
        ..., : metadata.original_samples
    ]
    output_parity = array_psnr(
        cpu_full.detach().cpu().numpy(), conditioned.detach().cpu().numpy()
    )
    write_wav_atomic(cpu_full, output_dir / "cpu-reference.wav")
    write_wav_atomic(conditioned, output_dir / "hybrid-qnn.wav")
    (output_dir / "payload.lwv").write_bytes(encoded.envelope_bytes)

    duration = metadata.original_samples / metadata.sample_rate
    code_payload_bps = len(encoded.envelope.payload) * 8 / duration
    checks = {
        "exact_sample_length": conditioned.shape[-1] == metadata.original_samples,
        "finite_output": bool(torch.isfinite(conditioned).all()),
        "approximately_1p5_kbps": 1_450 <= code_payload_bps <= 1_550,
        "strict_npu_tail": bool(
            npu_result.evidence["strict_no_fallback"]
            and npu_result.evidence["profile_cpu_node_count"] == 0
        ),
        "npu_tail_parity": tail_psnr >= 35.0,
        "conditioned_boundary_jump": maximum_boundary_jump(conditioned) <= 0.05,
    }
    experimental_manifest = json.loads(
        (PROJECT_ROOT / "artifacts/generated/audio_tail.manifest.json").read_text(
            encoding="utf-8"
        )
    )
    return {
        "schema_version": 1,
        "input": str(input_path),
        "summary": {
            "passed": all(checks.values()),
            "duration_seconds": duration,
            "envelope_bytes": len(encoded.envelope_bytes),
            "code_payload_bytes": len(encoded.envelope.payload),
            "code_payload_bps": code_payload_bps,
            "restored_samples": int(conditioned.shape[-1]),
            "raw_boundary_jump": maximum_boundary_jump(raw_waveform),
            "conditioned_boundary_jump": maximum_boundary_jump(conditioned),
            "npu_tail_psnr_db": tail_psnr,
            "full_cpu_to_hybrid_psnr_db": output_parity,
            "cpu_prefix_seconds": cpu_prefix_seconds,
            "npu_worker_seconds": npu_seconds,
        },
        "checks": checks,
        "execution_evidence": npu_result.evidence,
        "qdq_cpu_parity": experimental_manifest.get("cpu_quantized_parity"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "data/generated/demo-audio/chirp-and-tones.wav",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "reports/generated/audio-acceptance",
    )
    args = parser.parse_args()
    report = evaluate(args.input.resolve(), args.output_dir.resolve())
    report_path = args.output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["summary"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
