"""Native ARM64 worker for the fixed-shape EnCodec convolutional tail."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import onnxruntime_qnn as qnn

from .npu_worker import QNN_NAME, _device_evidence, _profile_providers


def run(
    model_path: Path,
    input_path: Path,
    output_path: Path,
    evidence_path: Path,
    profile_prefix: Path,
) -> None:
    prefixes = np.load(input_path, allow_pickle=False)
    if prefixes.ndim != 3 or prefixes.shape[1:] != (32, 24_000):
        raise ValueError(
            f"Expected audio prefixes [chunks,32,24000], got {prefixes.shape}."
        )
    if prefixes.dtype != np.float32:
        raise ValueError(f"Expected float32 audio prefixes, got {prefixes.dtype}.")

    ort.register_execution_provider_library(QNN_NAME, qnn.get_library_path())
    session = None
    try:
        npu_devices = [
            device
            for device in ort.get_ep_devices()
            if device.ep_name == QNN_NAME
            and device.device.type == ort.OrtHardwareDeviceType.NPU
        ]
        if len(npu_devices) != 1:
            raise RuntimeError(f"Expected one QNN NPU, found {len(npu_devices)}.")
        options = ort.SessionOptions()
        options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
        options.enable_profiling = True
        options.profile_file_prefix = str(profile_prefix)
        options.add_provider_for_devices(
            npu_devices, {"backend_path": qnn.get_qnn_htp_path()}
        )
        session_started = time.perf_counter()
        session = ort.InferenceSession(str(model_path), sess_options=options)
        session_seconds = time.perf_counter() - session_started
        outputs = []
        chunk_seconds = []
        run_options = ort.RunOptions()
        run_options.add_run_config_entry("qnn.perf_mode", "burst")
        for prefix in prefixes:
            started = time.perf_counter()
            result = session.run(None, {"prefix": prefix[None, ...]}, run_options)
            chunk_seconds.append(time.perf_counter() - started)
            outputs.append(np.asarray(result[0], dtype=np.float32))
        audio = np.concatenate(outputs, axis=0)
        if audio.shape != (prefixes.shape[0], 1, 24_000):
            raise RuntimeError(f"Unexpected audio-tail output shape: {audio.shape}.")
        if not np.isfinite(audio).all():
            raise RuntimeError("Audio tail returned non-finite values.")
        profile_path = Path(session.end_profiling())
        providers, cpu_nodes, event_count, provider_event_counts = _profile_providers(
            profile_path
        )
        if cpu_nodes:
            raise RuntimeError(f"Audio QNN profile contains {cpu_nodes} CPU nodes.")
        np.save(output_path, audio, allow_pickle=False)
        evidence = {
            "strict_no_fallback": True,
            "npu_selected": True,
            "selected_device": _device_evidence(npu_devices[0]),
            "onnxruntime_version": ort.__version__,
            "onnxruntime_qnn_version": qnn.__version__,
            "session_seconds": session_seconds,
            "chunk_inference_seconds": chunk_seconds,
            "profile_providers": providers,
            "profile_cpu_node_count": cpu_nodes,
            "profile_provider_event_count": event_count,
            "profile_provider_event_counts": provider_event_counts,
            "profile_filename": profile_path.name,
            "input_shape": list(prefixes.shape),
            "output_shape": list(audio.shape),
        }
        evidence_path.write_text(
            json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
        )
    finally:
        del session
        ort.unregister_execution_provider_library(QNN_NAME)


def main() -> None:
    from .offline import enforce_from_environment

    enforce_from_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--profile-prefix", type=Path, required=True)
    args = parser.parse_args()
    run(
        args.model.resolve(),
        args.input.resolve(),
        args.output.resolve(),
        args.evidence.resolve(),
        args.profile_prefix.resolve(),
    )


if __name__ == "__main__":
    main()
