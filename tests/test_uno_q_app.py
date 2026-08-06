from __future__ import annotations

import hashlib
import io
import json
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

UNO_PYTHON = Path(__file__).resolve().parents[1] / "uno_q" / "app" / "python"
sys.path.insert(0, str(UNO_PYTHON))

import lightweave_uno as uno  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fake_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> uno.Preset:
    app_root = tmp_path / "app"
    runtime = app_root / "runtime"
    runtime.mkdir(parents=True)
    preset = uno.PRESETS[0]
    paths = (
        runtime / "lightweave-uno-runner",
        runtime / "entropy_tables.bin",
        runtime / f"{preset.stem}.ncnn.param",
        runtime / f"{preset.stem}.ncnn.bin",
    )
    for index, path in enumerate(paths):
        path.write_bytes(f"fixture-{index}".encode())
    files = {
        path.relative_to(app_root).as_posix(): {
            "size": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in paths
    }
    manifest = {
        "schema_version": 1,
        "bundle_version": "test",
        "model_sha256": uno.MODEL_SHA256,
        "files": files,
    }
    manifest_path = app_root / "uno_q.manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(uno, "APP_ROOT", app_root)
    monkeypatch.setattr(uno, "RUNTIME_ROOT", runtime)
    monkeypatch.setattr(uno, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(uno, "ACCELERATOR_COOLDOWN_SECONDS", 0.0)
    monkeypatch.setattr(uno, "_LAST_ACCELERATOR_FINISH", 0.0)
    return preset


def _fake_audio_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app_root = tmp_path / "app"
    runtime = app_root / "runtime"
    runtime.mkdir(parents=True)
    paths = (
        runtime / "lightweave-uno-runner",
        runtime / "audio-codebooks.bin",
        runtime / "audio-prefix.ncnn.bin",
        runtime / "audio-prefix-1s.ncnn.param",
        runtime / "audio-tail.ncnn.param",
        runtime / "audio-tail.ncnn.bin",
    )
    for index, path in enumerate(paths):
        path.write_bytes(f"audio-fixture-{index}".encode())
    files = {
        path.relative_to(app_root).as_posix(): {
            "size": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in paths
    }
    manifest = {
        "schema_version": 1,
        "bundle_version": "test-audio",
        "model_sha256": uno.MODEL_SHA256,
        "audio_model_sha256": uno.AUDIO_MODEL_SHA256,
        "audio": {
            "model_sha256": uno.AUDIO_MODEL_SHA256,
            "selected_split": 5,
            "tail_channels": 32,
            "tail_frames_per_chunk": 1200,
            "maximum_seconds": 5,
        },
        "files": files,
    }
    manifest_path = app_root / "uno_q.manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(uno, "APP_ROOT", app_root)
    monkeypatch.setattr(uno, "RUNTIME_ROOT", runtime)
    monkeypatch.setattr(uno, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(uno, "ACCELERATOR_COOLDOWN_SECONDS", 0.0)
    monkeypatch.setattr(uno, "_LAST_ACCELERATOR_FINISH", 0.0)


def test_ppm_to_png_preserves_dimensions() -> None:
    pixels = bytes([255, 0, 0, 0, 255, 0])
    png, width, height = uno.ppm_to_png(b"P6\n2 1\n255\n" + pixels)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert (width, height) == (2, 1)
    assert png[-12:] == b"\x00\x00\x00\x00IEND\xaeB`\x82"


@pytest.mark.parametrize(
    "payload,code,message",
    [
        (b"", "I64-Q1-B128", "empty"),
        (b"x", "unknown", "Unsupported"),
        (b"x" * 129, "I64-Q1-B128", "at most 128"),
    ],
)
def test_decode_rejects_invalid_raw_contract(
    payload: bytes, code: str, message: str
) -> None:
    with pytest.raises(uno.UnoQError, match=message):
        uno.decode_payload(payload, code)


def test_decode_requires_strict_adreno_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preset = _fake_install(tmp_path, monkeypatch)

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        output = Path(command[command.index("--output") + 1])
        output.write_bytes(
            f"P6\n{preset.output_size} {preset.output_size}\n255\n".encode()
            + bytes(preset.output_size * preset.output_size * 3)
        )
        evidence = {
            "status": "ok",
            "backend": "ncnn-vulkan",
            "device": "Turnip Adreno 702",
            "strict_no_fallback": True,
            "compute_layers": 16,
            "entropy_seconds": 0.001,
            "inference_seconds": 0.2,
            "model_sha256": uno.MODEL_SHA256,
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(evidence), stderr="")

    monkeypatch.setattr(uno.subprocess, "run", fake_run)
    png, metrics = uno.decode_payload(b"valid", preset.code)
    assert png.startswith(b"\x89PNG")
    assert metrics["output_width"] == 64
    assert metrics["raw_bytes"] == 5
    assert metrics["strict_no_fallback"] is True

    def fallback_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        result = fake_run(command, **kwargs)
        evidence = json.loads(result.stdout)
        evidence["strict_no_fallback"] = False
        result.stdout = json.dumps(evidence)
        return result

    monkeypatch.setattr(uno.subprocess, "run", fallback_run)
    with pytest.raises(uno.UnoQError, match="strict Adreno"):
        uno.decode_payload(b"valid", preset.code)


def test_manifest_detects_artifact_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preset = _fake_install(tmp_path, monkeypatch)
    uno.validate_installation(preset)
    preset.parameter_path.write_bytes(b"changed")
    with pytest.raises(uno.UnoQError, match="check failed"):
        uno.validate_installation(preset)


@pytest.mark.parametrize(
    "payload,code,message",
    [
        (b"", "A1-E15-S24000", "empty"),
        (bytes(187), "A1-E15-S24000", "divisible by 188"),
        (bytes(941), "A1-E15-S120000", "5-second limit"),
        (bytes(187) + b"\x10", "A1-E15-S24000", "padding"),
        (bytes(188), "A1-E15-S24001", "impossible"),
        (bytes(376), "A1-E15-S24000", "impossible"),
        (bytes(188), "A1-E15", "Malformed"),
    ],
)
def test_audio_contract_rejects_invalid_payloads(
    payload: bytes, code: str, message: str
) -> None:
    with pytest.raises(uno.UnoQError, match=message):
        uno._raw_audio_contract(payload, code)


def test_audio_contract_accepts_one_and_five_seconds() -> None:
    assert uno._raw_audio_contract(bytes(188), "A1-E15-S1") == (1, 1)
    assert uno._raw_audio_contract(bytes(940), "A1-E15-S120000") == (
        120_000,
        5,
    )


def test_audio_decode_requires_strict_hybrid_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_audio_install(tmp_path, monkeypatch)

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        output = Path(command[command.index("--output") + 1])
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(24_000)
            stream.writeframes(bytes(24_000 * 2))
        output.write_bytes(wav_buffer.getvalue())
        evidence = {
            "status": "ok",
            "backend": "ncnn-hybrid-cpu-vulkan",
            "device": "Turnip Adreno 702",
            "strict_suffix_no_fallback": True,
            "selected_split": 5,
            "cpu_compute_layers": 24,
            "vulkan_compute_layers": 39,
            "model_sha256": uno.AUDIO_MODEL_SHA256,
            "output_samples": 24_000,
            "cpu_codebook_seconds": 0.001,
            "cpu_prefix_seconds": 0.2,
            "accelerator_seconds": 0.8,
            "postprocess_seconds": 0.001,
            "conditioned_maximum_boundary_jump": 0.0,
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(evidence), stderr="")

    monkeypatch.setattr(uno.subprocess, "run", fake_run)
    wav_data, metrics = uno.decode_audio_payload(bytes(188), "A1-E15-S24000")
    assert wav_data.startswith(b"RIFF")
    assert metrics["chunk_count"] == 1
    assert metrics["selected_split"] == 5
    assert metrics["strict_suffix_no_fallback"] is True

    def fallback_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        result = fake_run(command, **kwargs)
        evidence = json.loads(result.stdout)
        evidence["strict_suffix_no_fallback"] = False
        result.stdout = json.dumps(evidence)
        return result

    monkeypatch.setattr(uno.subprocess, "run", fallback_run)
    with pytest.raises(uno.UnoQError, match="CPU/Adreno audio path"):
        uno.decode_audio_payload(bytes(188), "A1-E15-S24000")


def test_uno_q_sbom_records_runtime_and_model_licenses() -> None:
    sbom_path = UNO_PYTHON.parents[1] / "SBOM.spdx.json"
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    assert sbom["spdxVersion"] == "SPDX-2.3"
    assert sbom["dataLicense"] == "CC0-1.0"
    packages = {item["name"]: item for item in sbom["packages"]}
    assert packages["LightWeave UNO Q receiver"]["licenseDeclared"] == "MIT"
    assert packages["ncnn"]["licenseDeclared"] == "BSD-3-Clause"
    assert packages["CompressAI"]["licenseDeclared"] == "BSD-3-Clause"
    assert packages["EnCodec"]["licenseDeclared"] == "MIT"
    checkpoint = packages["bmshj2018-factorized quality-1 checkpoint"]
    assert checkpoint["licenseDeclared"] == "NOASSERTION"
    assert "not committed" in checkpoint["comment"]
    audio_checkpoint = packages["EnCodec 24 kHz checkpoint"]
    assert audio_checkpoint["licenseDeclared"] == "NOASSERTION"
    assert "not committed" in audio_checkpoint["comment"]
