"""x64 controller for the native ARM64 EnCodec tail worker."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

from .errors import ModelMismatchError, NPUExecutionError
from .npu import NPUResult, _sha256, default_arm64_python
from .paths import generated_artifact_dir, project_root


def default_audio_tail_model() -> Path:
    configured = os.environ.get("LIGHTWEAVE_AUDIO_TAIL_ONNX")
    if configured:
        return Path(configured).expanduser().resolve()
    return generated_artifact_dir() / "audio_tail_qdq.onnx"


def _verify_audio_tail(model_path: Path, source_model_hash: bytes) -> None:
    manifest_path = generated_artifact_dir() / "audio_tail.manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            "The generated audio-tail manifest is missing. Run the audio export "
            "and quantization scripts."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("source_weights_sha256") != source_model_hash.hex():
        raise ModelMismatchError("The audio tail uses incompatible EnCodec weights.")
    expected_hashes = {
        value
        for value in (
            manifest.get("onnx_sha256"),
            manifest.get("quantized_onnx_sha256"),
        )
        if value
    }
    if _sha256(model_path) not in expected_hashes:
        raise ModelMismatchError("The audio-tail ONNX hash does not match.")


def reconstruct_audio_tail_on_npu(
    prefixes: Any,
    *,
    source_model_hash: bytes,
    arm64_python: Path | None = None,
    model_path: Path | None = None,
) -> NPUResult:
    interpreter = (arm64_python or default_arm64_python()).resolve()
    model = (model_path or default_audio_tail_model()).resolve()
    if not interpreter.is_file():
        raise FileNotFoundError(f"Native ARM64 Python not found: {interpreter}")
    if not model.is_file():
        raise FileNotFoundError(
            f"Quantized audio-tail model not found: {model}. Run model preparation."
        )
    _verify_audio_tail(model, source_model_hash)
    array = prefixes.detach().cpu().numpy().astype(np.float32, copy=False)
    with tempfile.TemporaryDirectory(prefix="lightweave-audio-npu-") as temp:
        work_dir = Path(temp)
        input_path = work_dir / "prefixes.npy"
        output_path = work_dir / "audio.npy"
        evidence_path = work_dir / "evidence.json"
        np.save(input_path, array, allow_pickle=False)
        command = [
            str(interpreter),
            "-m",
            "lightweave.audio_npu_worker",
            "--model",
            str(model),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--evidence",
            str(evidence_path),
            "--profile-prefix",
            str(work_dir / "qnn-audio-profile"),
        ]
        environment = os.environ.copy()
        source_path = str(project_root() / "src")
        environment["PYTHONPATH"] = os.pathsep.join(
            value
            for value in (source_path, environment.get("PYTHONPATH", ""))
            if value
        )
        started = time.perf_counter()
        completed = subprocess.run(
            command,
            cwd=project_root(),
            env=environment,
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )
        elapsed = time.perf_counter() - started
        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout).replace("\x00", "")
            raise NPUExecutionError(
                f"Strict audio QNN worker failed: {details[-4000:]}"
            )
        if not output_path.is_file() or not evidence_path.is_file():
            raise NPUExecutionError("Audio QNN worker did not create its outputs.")
        output = np.load(output_path, allow_pickle=False)
        evidence: dict[str, Any] = json.loads(
            evidence_path.read_text(encoding="utf-8")
        )
        if not evidence.get("strict_no_fallback") or not evidence.get("npu_selected"):
            raise NPUExecutionError("Audio tail did not prove strict NPU execution.")
        return NPUResult(output, evidence, elapsed)
