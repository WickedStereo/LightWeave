"""Prepare and validate native EnCodec receiver artifacts for Arduino UNO Q."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import ncnn
import numpy as np
import onnx
import onnxruntime as ort
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from export_audio_tail import (  # noqa: E402
    StreamingConv1dAsConv2d,
    replace_1d_convolutions,
)

from lightweave.audio import (  # noqa: E402
    CODEBOOK_COUNT,
    FRAMES_PER_CHUNK,
    SAMPLES_PER_CHUNK,
    condition_chunk_boundaries,
    load_audio_model,
    write_wav_atomic,
)
from lightweave.raw import pack_raw_audio_chunks  # noqa: E402

AUDIO_MODEL_SHA256 = "d7cc33bcf1aad7f2dad9836f36431530744abeace3ca033005e3290ed4fa47bf"
NCNN_VERSION = "20260526"
SPLIT_CANDIDATES = (2, 5, 8, 11, 13)
BOARD_GATE_EVIDENCE: dict[int, dict[str, object]] = {
    2: {
        "status": "rejected",
        "reason": "non-finite Adreno Vulkan output",
    },
    5: {
        "status": "passed",
        "device": "Turnip Adreno 702",
        "vulkan_compute_layers": 39,
        "strict_suffix_no_fallback": True,
        "one_second_pytorch_parity_db": 52.1066,
        "five_second_pytorch_parity_db": 52.0681,
    },
}
SPLIT_SHAPES = {
    2: (512, 75),
    5: (256, 600),
    8: (128, 3_000),
    11: (64, 12_000),
    13: (32, 24_000),
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class AudioPrefix(torch.nn.Module):
    def __init__(self, model: torch.nn.Module, split: int) -> None:
        super().__init__()
        layers = list(model.decoder.model.children())
        self.initial = StreamingConv1dAsConv2d(layers[0])
        self.lstm = layers[1]
        self.rest = torch.nn.Sequential(*layers[2:split])
        replace_1d_convolutions(self.rest)

    def forward(self, embedding: torch.Tensor) -> torch.Tensor:
        value = self.initial(embedding.unsqueeze(3)).squeeze(3)
        value = self.lstm(value)
        if len(self.rest):
            value = self.rest(value.unsqueeze(3)).squeeze(3)
        return value


class AudioSuffix(torch.nn.Module):
    def __init__(self, model: torch.nn.Module, split: int) -> None:
        super().__init__()
        self.layers = torch.nn.Sequential(*list(model.decoder.model.children())[split:])
        replace_1d_convolutions(self.layers)

    def forward(self, prefix: torch.Tensor) -> torch.Tensor:
        return self.layers(prefix)


def write_codebooks(path: Path, weights: Path | None) -> dict[str, object]:
    model, weight_path, fingerprint = load_audio_model(weights)
    if fingerprint.hex() != AUDIO_MODEL_SHA256:
        raise RuntimeError("UNO Q audio requires the pinned EnCodec checkpoint.")
    values = []
    for index in range(CODEBOOK_COUNT):
        table = (
            model.quantizer.vq.layers[index]
            ._codebook.embed.detach()
            .cpu()
            .to(torch.float32)
            .numpy()
        )
        if table.shape != (1024, 128) or not np.isfinite(table).all():
            raise RuntimeError("Unexpected EnCodec codebook shape or values.")
        values.append(np.asarray(table, dtype="<f4"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(struct.pack("<4sHHHH", b"LWCB", 1, 2, 1024, 128))
        stream.write(fingerprint)
        for table in values:
            stream.write(table.tobytes(order="C"))
    return {
        "path": str(path.resolve()),
        "sha256": file_sha256(path),
        "format": "LWCB-v1-little-endian",
        "codebooks": 2,
        "entries": 1024,
        "dimension": 128,
        "source_weights": str(weight_path),
        "source_weights_sha256": fingerprint.hex(),
    }


def _quality(reference: np.ndarray, actual: np.ndarray) -> dict[str, object]:
    if actual.shape != reference.shape or not np.isfinite(actual).all():
        raise RuntimeError("Converted audio graph returned invalid output.")
    difference = actual.astype(np.float64) - reference.astype(np.float64)
    mse = float(np.mean(np.square(difference)))
    peak = max(1.0, float(np.max(np.abs(reference))))
    # Keep manifests strict-JSON even when conversion is bit-exact.
    psnr = 300.0 if mse == 0 else 10 * math.log10(peak * peak / mse)
    result = {
        "psnr_db": psnr,
        "maximum_absolute_error": float(np.max(np.abs(difference))),
        "mean_absolute_error": float(np.mean(np.abs(difference))),
        "threshold_db": 35.0,
        "passed": psnr >= 35.0,
    }
    if not result["passed"]:
        raise RuntimeError(f"Audio conversion parity failed: {result}.")
    return result


def export_onnx(
    wrapper: torch.nn.Module,
    sample: torch.Tensor,
    reference: np.ndarray,
    output: Path,
    input_name: str,
    output_name: str,
) -> dict[str, object]:
    output.parent.mkdir(parents=True, exist_ok=True)
    with torch.inference_mode():
        rewritten = wrapper(sample).cpu().numpy()
        rewrite_parity = _quality(reference, rewritten)
        torch.onnx.export(
            wrapper,
            (sample,),
            output,
            input_names=[input_name],
            output_names=[output_name],
            opset_version=18,
            do_constant_folding=True,
            dynamo=False,
        )
    graph = onnx.load(output)
    onnx.checker.check_model(graph)
    session = ort.InferenceSession(str(output), providers=["CPUExecutionProvider"])
    actual = session.run(None, {input_name: sample.cpu().numpy()})[0]
    return {
        "path": str(output.resolve()),
        "sha256": file_sha256(output),
        "input_name": input_name,
        "input_shape": list(sample.shape),
        "output_name": output_name,
        "output_shape": list(actual.shape),
        "rewrite_parity": rewrite_parity,
        "onnx_parity": _quality(reference, actual),
    }


def convert_with_pnnx(
    pnnx: Path,
    onnx_path: Path,
    output_dir: Path,
    stem: str,
    input_shape: tuple[int, ...],
) -> tuple[Path, Path]:
    param_path = output_dir / f"{stem}.ncnn.param"
    bin_path = output_dir / f"{stem}.ncnn.bin"
    shape = ",".join(str(value) for value in input_shape)
    command = [
        str(pnnx),
        str(onnx_path),
        f"inputshape=[{shape}]",
        f"pnnxparam={output_dir / f'{stem}.pnnx.param'}",
        f"pnnxbin={output_dir / f'{stem}.pnnx.bin'}",
        f"pnnxpy={output_dir / f'{stem}_pnnx.py'}",
        f"pnnxonnx={output_dir / f'{stem}.pnnx.onnx'}",
        f"ncnnparam={param_path}",
        f"ncnnbin={bin_path}",
        f"ncnnpy={output_dir / f'{stem}_ncnn.py'}",
        "fp16=1",
        "optlevel=2",
        "device=cpu",
    ]
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    if not param_path.is_file() or not bin_path.is_file():
        raise RuntimeError(f"pnnx did not create {stem} artifacts.")
    return param_path, bin_path


def ncnn_cpu_output(parameter: Path, weights: Path, value: np.ndarray) -> np.ndarray:
    with ncnn.Net() as net:
        net.opt.use_vulkan_compute = False
        net.opt.use_fp16_storage = True
        net.opt.use_fp16_packed = True
        net.opt.use_fp16_arithmetic = False
        if net.load_param(str(parameter)) != 0 or net.load_model(str(weights)) != 0:
            raise RuntimeError("Python ncnn could not load an audio graph.")
        with net.create_extractor() as extractor:
            input_value = np.asarray(value.squeeze(0), dtype=np.float32)
            if extractor.input("in0", ncnn.Mat(input_value).clone()) != 0:
                raise RuntimeError("Python ncnn rejected an audio input.")
            status, output = extractor.extract("out0")
            if status != 0:
                raise RuntimeError("Python ncnn failed audio inference.")
            return np.asarray(output, dtype=np.float32)[None, ...]


def prepare_prefix(
    pnnx: Path,
    output_dir: Path,
    weights: Path | None,
    split: int,
    seconds: int,
) -> dict[str, object]:
    model, _, _ = load_audio_model(weights)
    generator = torch.Generator().manual_seed(20260805 + split * 100 + seconds)
    sample = (
        torch.randn((1, 128, FRAMES_PER_CHUNK * seconds), generator=generator) * 0.05
    )
    with torch.inference_mode():
        reference = model.decoder.model[:split](sample).cpu().numpy()
    wrapper = AudioPrefix(model, split).eval()
    stem = f"candidate-s{split}-prefix-{seconds}s"
    onnx_path = output_dir / f"{stem}.fp32.onnx"
    exported = export_onnx(wrapper, sample, reference, onnx_path, "embedding", "prefix")
    param_path, bin_path = convert_with_pnnx(
        pnnx, onnx_path, output_dir, stem, tuple(sample.shape)
    )
    actual = ncnn_cpu_output(param_path, bin_path, sample.numpy())
    return {
        "seconds": seconds,
        "parameter_path": str(param_path.resolve()),
        "parameter_sha256": file_sha256(param_path),
        "weights_path": str(bin_path.resolve()),
        "weights_sha256": file_sha256(bin_path),
        "onnx": exported,
        "ncnn_cpu_parity": _quality(reference, actual),
    }


def prepare_suffix(
    pnnx: Path, output_dir: Path, weights: Path | None, split: int
) -> dict[str, object]:
    model, _, _ = load_audio_model(weights)
    channels, frames = SPLIT_SHAPES[split]
    generator = torch.Generator().manual_seed(20260805 + split)
    sample_3d = torch.randn((1, channels, frames), generator=generator) * 0.05
    with torch.inference_mode():
        reference = model.decoder.model[split:](sample_3d).unsqueeze(3).cpu().numpy()
    sample = sample_3d.unsqueeze(3)
    wrapper = AudioSuffix(model, split).eval()
    stem = f"candidate-s{split}-tail"
    onnx_path = output_dir / f"{stem}.fp32.onnx"
    exported = export_onnx(
        wrapper, sample, reference, onnx_path, "prefix", "audio_chunk"
    )
    param_path, bin_path = convert_with_pnnx(
        pnnx, onnx_path, output_dir, stem, tuple(sample.shape)
    )
    actual = ncnn_cpu_output(param_path, bin_path, sample.numpy())
    return {
        "split": split,
        "input_shape": [1, channels, frames, 1],
        "output_shape": [1, 1, SAMPLES_PER_CHUNK, 1],
        "parameter_path": str(param_path.resolve()),
        "parameter_sha256": file_sha256(param_path),
        "weights_path": str(bin_path.resolve()),
        "weights_sha256": file_sha256(bin_path),
        "onnx": exported,
        "ncnn_cpu_parity": _quality(reference, actual),
    }


def make_fixture(
    output_dir: Path, weights: Path | None, split: int
) -> dict[str, object]:
    model, _, _ = load_audio_model(weights)
    timeline = torch.arange(SAMPLES_PER_CHUNK, dtype=torch.float32) / 24_000
    waveform = (
        0.20 * torch.sin(2 * torch.pi * 220 * timeline)
        + 0.08 * torch.sin(2 * torch.pi * 660 * timeline)
    ).reshape(1, 1, -1)
    with torch.inference_mode():
        frames = model.encode(waveform)
        codes = frames[0][0]
        payload = pack_raw_audio_chunks(codes)
        embedding = model.quantizer.decode(codes.transpose(0, 1))
        prefix = model.decoder.model[:split](embedding)
        chunk = model.decoder.model[split:](prefix)
        reference = condition_chunk_boundaries(chunk)
    if len(payload) != 188 or tuple(reference.shape) != (1, 1, 24_000):
        raise RuntimeError("UNO Q audio fixture violates the raw contract.")
    payload_path = output_dir / "audio.payload.bin"
    wav_path = output_dir / f"candidate-s{split}.reference.wav"
    payload_path.write_bytes(payload)
    write_wav_atomic(reference, wav_path)
    return {
        "preset_code": "A1-E15-S24000",
        "payload_path": str(payload_path.resolve()),
        "payload_sha256": file_sha256(payload_path),
        "reference_wav": str(wav_path.resolve()),
        "reference_wav_sha256": file_sha256(wav_path),
    }


def resolve_pnnx(value: Path | None) -> Path:
    candidate = value.resolve() if value else None
    if candidate is None:
        executable = shutil.which("pnnx")
        if executable:
            candidate = Path(executable).resolve()
    if candidate is None or not candidate.is_file():
        raise RuntimeError("pnnx 20260526 is required for UNO Q audio models.")
    return candidate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "generated" / "uno_q" / "audio",
    )
    parser.add_argument("--weights", type=Path)
    parser.add_argument("--pnnx", type=Path)
    parser.add_argument(
        "--selected-split", type=int, choices=SPLIT_CANDIDATES, default=5
    )
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    pnnx = resolve_pnnx(args.pnnx)

    candidates = []
    for split in SPLIT_CANDIDATES:
        candidates.append(
            {
                "split": split,
                "one_second_prefix": prepare_prefix(
                    pnnx, output_dir, args.weights, split, 1
                ),
                "suffix": prepare_suffix(pnnx, output_dir, args.weights, split),
                "board_gate": BOARD_GATE_EVIDENCE.get(
                    split,
                    {
                        "status": "not required",
                        "reason": "an earlier candidate passed",
                    },
                ),
            }
        )

    selected_prefixes = []
    first = next(item for item in candidates if item["split"] == args.selected_split)[
        "one_second_prefix"
    ]
    selected_prefixes.append(first)
    for seconds in range(2, 6):
        selected_prefixes.append(
            prepare_prefix(pnnx, output_dir, args.weights, args.selected_split, seconds)
        )
    weight_hashes = {str(item["weights_sha256"]) for item in selected_prefixes}
    if len(weight_hashes) != 1:
        raise RuntimeError("Static audio prefixes did not share identical weights.")
    shared_prefix_bin = output_dir / "audio-prefix.ncnn.bin"
    shutil.copy2(Path(str(selected_prefixes[0]["weights_path"])), shared_prefix_bin)
    for item in selected_prefixes:
        seconds = int(item["seconds"])
        target = output_dir / f"audio-prefix-{seconds}s.ncnn.param"
        shutil.copy2(Path(str(item["parameter_path"])), target)
        item["installed_parameter_path"] = str(target.resolve())
        item["installed_parameter_sha256"] = file_sha256(target)

    selected_candidate = next(
        item for item in candidates if item["split"] == args.selected_split
    )
    selected_tail = selected_candidate["suffix"]
    tail_param = output_dir / "audio-tail.ncnn.param"
    tail_bin = output_dir / "audio-tail.ncnn.bin"
    shutil.copy2(Path(str(selected_tail["parameter_path"])), tail_param)
    shutil.copy2(Path(str(selected_tail["weights_path"])), tail_bin)

    result = {
        "schema_version": 1,
        "target": "Arduino UNO Q / Debian ARM64 / CPU plus Adreno Vulkan",
        "profile": "A1-E15-S<n>",
        "maximum_seconds": 5,
        "maximum_payload_bytes": 940,
        "sample_rate": 24000,
        "chunk_bytes": 188,
        "model_sha256": AUDIO_MODEL_SHA256,
        "selected_split": args.selected_split,
        "selection_policy": "earliest candidate passing board parity and stability",
        "tools": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "onnxruntime": ort.__version__,
            "pnnx": NCNN_VERSION,
            "ncnn_python": getattr(ncnn, "__version__", NCNN_VERSION),
        },
        "codebooks": write_codebooks(output_dir / "audio-codebooks.bin", args.weights),
        "candidates": candidates,
        "selected": {
            "split": args.selected_split,
            "tail_channels": SPLIT_SHAPES[args.selected_split][0],
            "tail_frames_per_chunk": SPLIT_SHAPES[args.selected_split][1],
            "prefix_weights_path": str(shared_prefix_bin.resolve()),
            "prefix_weights_sha256": file_sha256(shared_prefix_bin),
            "prefixes": selected_prefixes,
            "tail_parameter_path": str(tail_param.resolve()),
            "tail_parameter_sha256": file_sha256(tail_param),
            "tail_weights_path": str(tail_bin.resolve()),
            "tail_weights_sha256": file_sha256(tail_bin),
        },
        "fixture": make_fixture(output_dir, args.weights, args.selected_split),
    }
    manifest = output_dir / "audio.manifest.json"
    manifest.write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "ok", "manifest": str(manifest)}, indent=2))


if __name__ == "__main__":
    main()
