"""x64 controller for the native ARM64 QNN worker."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .errors import ModelMismatchError, NPUExecutionError
from .paths import generated_artifact_dir, project_root


@dataclass(slots=True)
class NPUResult:
    output: np.ndarray
    evidence: dict[str, Any]
    elapsed_seconds: float


def default_arm64_python() -> Path:
    configured = os.environ.get("LIGHTWEAVE_ARM64_PYTHON")
    if configured:
        return Path(configured).expanduser().resolve()
    return project_root() / ".venv-arm64" / "Scripts" / "python.exe"


def default_decoder_model() -> Path:
    configured = os.environ.get("LIGHTWEAVE_IMAGE_DECODER_ONNX")
    if configured:
        return Path(configured).expanduser().resolve()
    return generated_artifact_dir() / "image_decoder_qdq.onnx"


def default_raw_decoder_model() -> Path:
    configured = os.environ.get("LIGHTWEAVE_RAW_IMAGE_DECODER_ONNX")
    if configured:
        return Path(configured).expanduser().resolve()
    return generated_artifact_dir() / "raw_image_decoder_qdq.onnx"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_local_decoder(
    model_path: Path, source_model_hash: bytes, manifest_path: Path
) -> None:
    if not manifest_path.is_file():
        raise FileNotFoundError(
            "The generated decoder manifest is missing. Run "
            "`python scripts/export_image_decoder.py` in the x64 environment."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("source_weights_sha256") != source_model_hash.hex():
        raise ModelMismatchError(
            "The generated ONNX decoder was exported from different model weights."
        )
    actual_onnx_hash = _sha256(model_path)
    expected_hashes = {
        value
        for value in (
            manifest.get("onnx_sha256"),
            manifest.get("quantized_onnx_sha256"),
        )
        if value
    }
    if actual_onnx_hash not in expected_hashes:
        raise ModelMismatchError(
            "The generated ONNX decoder hash does not match its local manifest."
        )


def reconstruct_on_npu(
    latent: Any,
    *,
    source_model_hash: bytes,
    arm64_python: Path | None = None,
    model_path: Path | None = None,
    manifest_path: Path | None = None,
    raw_image: bool = False,
) -> NPUResult:
    interpreter = (arm64_python or default_arm64_python()).resolve()
    decoder = (
        model_path
        or (default_raw_decoder_model() if raw_image else default_decoder_model())
    ).resolve()
    local_manifest = (
        manifest_path
        or generated_artifact_dir()
        / (
            "raw_image_decoder.manifest.json"
            if raw_image
            else "image_decoder.manifest.json"
        )
    ).resolve()
    if not interpreter.is_file():
        raise FileNotFoundError(
            f"Native ARM64 Python was not found at {interpreter}. Set "
            "LIGHTWEAVE_ARM64_PYTHON to the correct interpreter."
        )
    if not decoder.is_file():
        raise FileNotFoundError(
            f"The QNN decoder model was not found at {decoder}. Run the export script."
        )
    _verify_local_decoder(decoder, source_model_hash, local_manifest)

    array = latent.detach().cpu().numpy().astype(np.float32, copy=False)
    with tempfile.TemporaryDirectory(prefix="lightweave-npu-") as directory:
        work_dir = Path(directory)
        input_path = work_dir / "latent.npy"
        output_path = work_dir / "reconstructed.npy"
        evidence_path = work_dir / "evidence.json"
        profile_prefix = work_dir / "qnn-profile"
        np.save(input_path, array, allow_pickle=False)

        command = [
            str(interpreter),
            "-m",
            "lightweave.npu_worker",
            "--model",
            str(decoder),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--evidence",
            str(evidence_path),
            "--profile-prefix",
            str(profile_prefix),
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
                "The strict QNN worker failed with exit code "
                f"{completed.returncode}: {details[-4000:]}"
            )
        if not output_path.is_file() or not evidence_path.is_file():
            raise NPUExecutionError(
                "The QNN worker did not produce its required outputs."
            )
        output = np.load(output_path, allow_pickle=False)
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if not evidence.get("strict_no_fallback") or not evidence.get("npu_selected"):
            raise NPUExecutionError(
                "The QNN worker did not prove strict NPU execution."
            )
        return NPUResult(output, evidence, elapsed)
