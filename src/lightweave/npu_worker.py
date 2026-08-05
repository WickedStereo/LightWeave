"""Native ARM64 worker that runs one fixed-shape decoder on QNN HTP."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
import onnxruntime_qnn as qnn

QNN_NAME = "QNNExecutionProvider"


def _device_evidence(ep_device: Any) -> dict[str, object]:
    device = ep_device.device
    return {
        "ep_name": ep_device.ep_name,
        "ep_vendor": ep_device.ep_vendor,
        "hardware_type": str(device.type),
        "hardware_vendor": device.vendor,
        "vendor_id": device.vendor_id,
        "device_id": device.device_id,
        "device_metadata": dict(device.metadata),
        "ep_metadata": {
            key: Path(value).name if key == "library_path" else value
            for key, value in dict(ep_device.ep_metadata).items()
        },
    }


def _profile_providers(profile_path: Path) -> tuple[list[str], int]:
    if not profile_path.is_file():
        return [], 0
    events = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    providers: set[str] = set()
    cpu_nodes = 0
    for event in events:
        provider = event.get("args", {}).get("provider")
        if provider:
            providers.add(str(provider))
            if str(provider) == "CPUExecutionProvider":
                cpu_nodes += 1
    return sorted(providers), cpu_nodes


def run(
    model_path: Path,
    input_path: Path,
    output_path: Path,
    evidence_path: Path,
    profile_prefix: Path,
) -> None:
    latent = np.load(input_path, allow_pickle=False)
    if (
        latent.ndim != 4
        or latent.shape[0] != 1
        or latent.shape[1] != 192
        or latent.shape[2] <= 0
        or latent.shape[3] <= 0
        or latent.dtype != np.float32
    ):
        raise ValueError(
            "The image NPU worker requires float32 latent shape [1,192,H,W]; "
            f"got {latent.shape} {latent.dtype}."
        )

    ort.register_execution_provider_library(QNN_NAME, qnn.get_library_path())
    session = None
    try:
        devices = ort.get_ep_devices()
        npu_devices = [
            device
            for device in devices
            if device.ep_name == QNN_NAME
            and device.device.type == ort.OrtHardwareDeviceType.NPU
        ]
        if len(npu_devices) != 1:
            raise RuntimeError(
                f"Expected exactly one QNN NPU device, found {len(npu_devices)}."
            )

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

        inputs = session.get_inputs()
        if len(inputs) != 1 or inputs[0].name != "latent":
            raise RuntimeError("The NPU decoder has an unexpected input contract.")
        if tuple(inputs[0].shape) != tuple(latent.shape):
            raise RuntimeError(
                f"Decoder input shape {inputs[0].shape} does not match "
                f"latent shape {latent.shape}."
            )
        outputs = session.get_outputs()
        if len(outputs) != 1 or outputs[0].name != "image":
            raise RuntimeError("The NPU decoder has an unexpected output contract.")
        expected_output_shape = tuple(outputs[0].shape)
        if not all(isinstance(value, int) for value in expected_output_shape):
            raise RuntimeError("The NPU decoder output shape must be fully static.")
        run_options = ort.RunOptions()
        run_options.add_run_config_entry("qnn.perf_mode", "burst")
        inference_started = time.perf_counter()
        result = session.run(None, {"latent": latent}, run_options)
        inference_seconds = time.perf_counter() - inference_started
        if len(result) != 1:
            raise RuntimeError("The NPU decoder returned an unexpected output count.")
        reconstructed = np.asarray(result[0], dtype=np.float32)
        if reconstructed.shape != expected_output_shape:
            raise RuntimeError(
                f"Unexpected NPU decoder output shape: {reconstructed.shape}."
            )
        if not np.isfinite(reconstructed).all():
            raise RuntimeError("The NPU decoder returned non-finite values.")

        profile_path = Path(session.end_profiling())
        providers, cpu_node_count = _profile_providers(profile_path)
        if cpu_node_count:
            raise RuntimeError(
                f"QNN profile reported {cpu_node_count} CPU-executed nodes."
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(output_path, reconstructed, allow_pickle=False)
        evidence = {
            "strict_no_fallback": True,
            "npu_selected": True,
            "selected_device": _device_evidence(npu_devices[0]),
            "onnxruntime_version": ort.__version__,
            "onnxruntime_qnn_version": qnn.__version__,
            "session_seconds": session_seconds,
            "inference_seconds": inference_seconds,
            "profile_providers": providers,
            "profile_cpu_node_count": cpu_node_count,
            "profile_filename": profile_path.name,
            "input_shape": list(latent.shape),
            "output_shape": list(reconstructed.shape),
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
