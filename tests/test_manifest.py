from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_tracked_model_manifest_records_validated_conversion_contracts() -> None:
    manifest = json.loads(
        (PROJECT_ROOT / "models/manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["schema_version"] == 1
    assert manifest["audio"]["status"] == "validated-hybrid-qnn"

    image_onnx = manifest["image"]["onnx"]
    assert manifest["image"]["latent_shape"] == [1, 192, 16, 16]
    assert image_onnx["quantization"] == {
        "format": "QDQ",
        "activation_type": "QUInt16",
        "weight_type": "QUInt16",
        "calibration_method": "MinMax",
        "calibration_source": "data/demo_manifest.json acceptance image latents",
        "cpu_fallback": False,
    }
    raw_image = manifest["image"]["raw"]
    assert raw_image["default_preset"] == "I128-Q1-B768"
    assert raw_image["legacy_aliases"] == {"I64-Q1": "I64-Q1-B128"}
    assert raw_image["wire_fields"] == []
    assert [item["maximum_payload_bytes"] for item in raw_image["presets"]] == [
        128,
        768,
        2048,
    ]
    assert [item["latent_shape"] for item in raw_image["presets"]] == [
        [1, 192, 4, 4],
        [1, 192, 8, 8],
        [1, 192, 16, 16],
    ]
    assert raw_image["quantization"]["cpu_fallback"] is False

    audio = manifest["audio"]
    audio_onnx = audio["onnx"]
    assert audio_onnx["input_shape"] == [1, 32, 24000]
    assert audio_onnx["output_shape"] == [1, 1, 24000]
    assert audio["decoder_partition"]["qnn_htp"] == ("fixed-shape decoder layers 13-15")
    assert audio_onnx["quantization"]["activation_type"] == "QUInt16"
    assert audio_onnx["quantization"]["weight_type"] == "QUInt8"
    assert audio_onnx["quantization"]["cpu_fallback"] is False
    uno_audio = audio["uno_q"]
    assert uno_audio["maximum_seconds"] == 5
    assert uno_audio["maximum_payload_bytes"] == 940
    assert uno_audio["decoder_partition"]["selected_split"] == 5
    assert uno_audio["decoder_partition"]["strict_suffix_no_fallback"] is True
    assert uno_audio["decoder_partition"]["vulkan_compute_layers"] == 39
    assert uno_audio["numerical_evidence"]["one_second_pytorch_parity_db"] >= 35
    assert uno_audio["numerical_evidence"]["five_second_pytorch_parity_db"] >= 35


def test_example_environment_exposes_all_supported_path_overrides() -> None:
    example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    for variable in (
        "LIGHTWEAVE_MODEL_DIR",
        "LIGHTWEAVE_IMAGE_WEIGHTS",
        "LIGHTWEAVE_AUDIO_WEIGHTS",
        "LIGHTWEAVE_ARM64_PYTHON",
        "LIGHTWEAVE_IMAGE_DECODER_ONNX",
        "LIGHTWEAVE_RAW_IMAGE_DECODER_ONNX",
        "LIGHTWEAVE_RAW_IMAGE_128_DECODER_ONNX",
        "LIGHTWEAVE_AUDIO_TAIL_ONNX",
        "LIGHTWEAVE_ENFORCE_OFFLINE",
    ):
        assert f"{variable}=" in example
