"""Verify that ONNX Runtime can execute a model on the QNN HTP backend.

This script is intentionally dependency-light and is meant to be run with the
native ARM64 environment. It disables CPU fallback, so a successful result is
evidence that the complete supplied graph was accepted by QNN.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
import onnxruntime_qnn as qnn

QNN_REGISTRATION_NAME = "QNNExecutionProvider"


def _shape_from_input(input_info: Any) -> tuple[int, ...]:
    shape: list[int] = []
    for dimension in input_info.shape:
        if not isinstance(dimension, int) or dimension <= 0:
            raise ValueError(
                "The probe requires a fixed positive input shape; "
                f"got {input_info.shape!r}."
            )
        shape.append(dimension)
    return tuple(shape)


def _dtype_from_onnx(type_name: str) -> np.dtype[Any]:
    types: dict[str, np.dtype[Any]] = {
        "tensor(float)": np.dtype(np.float32),
        "tensor(float16)": np.dtype(np.float16),
        "tensor(uint8)": np.dtype(np.uint8),
        "tensor(int8)": np.dtype(np.int8),
        "tensor(int32)": np.dtype(np.int32),
        "tensor(int64)": np.dtype(np.int64),
    }
    try:
        return types[type_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported probe input type: {type_name}") from exc


def probe(model_path: Path) -> None:
    if not model_path.is_file():
        raise FileNotFoundError(model_path)

    print(f"onnxruntime={ort.__version__}")
    print(f"onnxruntime-qnn={qnn.__version__}")

    ort.register_execution_provider_library(
        QNN_REGISTRATION_NAME, qnn.get_library_path()
    )
    try:
        devices = ort.get_ep_devices()
        for device in devices:
            hardware_device = getattr(device, "device", None)
            hardware_type = getattr(hardware_device, "type", "unreported")
            print(
                f"device={device.ep_name};hardware_type={hardware_type};details={device}"
            )

        qnn_devices = [
            device
            for device in devices
            if device.ep_name == QNN_REGISTRATION_NAME
            and device.device.type == ort.OrtHardwareDeviceType.NPU
        ]
        if not qnn_devices:
            raise RuntimeError(
                "The QNN plugin registered but did not expose a QNN NPU device."
            )

        options = ort.SessionOptions()
        options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
        options.add_provider_for_devices(
            qnn_devices, {"backend_path": qnn.get_qnn_htp_path()}
        )
        session = ort.InferenceSession(str(model_path), sess_options=options)

        if len(session.get_inputs()) != 1:
            raise ValueError("The generic probe currently supports one model input.")
        input_info = session.get_inputs()[0]
        shape = _shape_from_input(input_info)
        dtype = _dtype_from_onnx(input_info.type)
        print(f"input={input_info.name};shape={shape};dtype={dtype.name}")

        feeds = {input_info.name: np.zeros(shape, dtype=dtype)}
        run_options = ort.RunOptions()
        run_options.add_run_config_entry("qnn.perf_mode", "burst")
        outputs = session.run(None, feeds, run_options)

        if not outputs:
            raise RuntimeError("The QNN session returned no outputs.")
        output = np.asarray(outputs[0])
        print(
            f"output_shape={output.shape};dtype={output.dtype};"
            f"finite={bool(np.isfinite(output).all())}"
        )
        if not np.isfinite(output).all():
            raise RuntimeError("The QNN output contains non-finite values.")
        print("QNN_NO_FALLBACK_PROBE=PASS")
    finally:
        ort.unregister_execution_provider_library(QNN_REGISTRATION_NAME)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path, help="Fixed-shape ONNX model to run")
    args = parser.parse_args()
    probe(args.model.resolve())


if __name__ == "__main__":
    main()
