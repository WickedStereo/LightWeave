"""Export and validate the fixed 75-frame EnCodec convolutional tail."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch
import torch.nn.functional as functional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightweave.audio import AUDIO_NPU_SPLIT_INDEX, load_audio_model  # noqa: E402
from lightweave.paths import generated_artifact_dir  # noqa: E402


class StreamingConv1dAsConv2d(torch.nn.Module):
    def __init__(self, source: torch.nn.Module) -> None:
        super().__init__()
        convolution = source.conv.conv
        self.causal = source.causal
        self.pad_mode = source.pad_mode
        self.kernel_size = convolution.kernel_size[0]
        self.stride = convolution.stride[0]
        self.dilation = convolution.dilation[0]
        self.conv = torch.nn.Conv2d(
            convolution.in_channels,
            convolution.out_channels,
            kernel_size=(self.kernel_size, 1),
            stride=(self.stride, 1),
            dilation=(self.dilation, 1),
            groups=convolution.groups,
            bias=convolution.bias is not None,
        )
        with torch.no_grad():
            self.conv.weight.copy_(convolution.weight.detach().unsqueeze(3))
            if convolution.bias is not None:
                self.conv.bias.copy_(convolution.bias.detach())

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        padding_total = (self.kernel_size - 1) * self.dilation - (self.stride - 1)
        length = value.shape[-2]
        frame_count = (length - self.kernel_size + padding_total) / self.stride + 1
        ideal_length = (
            (math.ceil(frame_count) - 1) * self.stride
            + self.kernel_size
            - padding_total
        )
        extra_padding = ideal_length - length
        if self.causal:
            left, right = padding_total, extra_padding
        else:
            right = padding_total // 2
            left = padding_total - right
            right += extra_padding
        padded = functional.pad(
            value, (0, 0, left, right), mode=self.pad_mode
        )
        return self.conv(padded)


class StreamingConvTranspose1dAsConvTranspose2d(torch.nn.Module):
    def __init__(self, source: torch.nn.Module) -> None:
        super().__init__()
        convolution = source.convtr.convtr
        self.causal = source.causal
        self.trim_right_ratio = source.trim_right_ratio
        self.kernel_size = convolution.kernel_size[0]
        self.stride = convolution.stride[0]
        self.conv = torch.nn.ConvTranspose2d(
            convolution.in_channels,
            convolution.out_channels,
            kernel_size=(self.kernel_size, 1),
            stride=(self.stride, 1),
            groups=convolution.groups,
            bias=convolution.bias is not None,
        )
        with torch.no_grad():
            self.conv.weight.copy_(convolution.weight.detach().unsqueeze(3))
            if convolution.bias is not None:
                self.conv.bias.copy_(convolution.bias.detach())

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        output = self.conv(value)
        padding_total = self.kernel_size - self.stride
        if self.causal:
            right = math.ceil(padding_total * self.trim_right_ratio)
            left = padding_total - right
        else:
            right = padding_total // 2
            left = padding_total - right
        end = output.shape[-2] - right if right else output.shape[-2]
        return output[..., left:end, :]


def replace_1d_convolutions(module: torch.nn.Module) -> None:
    for name, child in list(module.named_children()):
        class_name = child.__class__.__name__
        if class_name == "SConv1d":
            setattr(module, name, StreamingConv1dAsConv2d(child))
        elif class_name == "SConvTranspose1d":
            setattr(module, name, StreamingConvTranspose1dAsConvTranspose2d(child))
        else:
            replace_1d_convolutions(child)


class AudioTail(torch.nn.Module):
    def __init__(self, model: torch.nn.Module) -> None:
        super().__init__()
        self.tail = torch.nn.Sequential(
            *list(model.decoder.model.children())[AUDIO_NPU_SPLIT_INDEX:]
        )
        replace_1d_convolutions(self.tail)

    def forward(self, prefix: torch.Tensor) -> torch.Tensor:
        return self.tail(prefix.unsqueeze(3)).squeeze(3)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def export_tail(output: Path) -> dict[str, object]:
    model, weight_path, weight_hash = load_audio_model()
    generator = torch.Generator().manual_seed(20260805)
    prefix = torch.randn((1, 32, 24_000), generator=generator) * 0.1
    with torch.inference_mode():
        original_reference = model.decoder.model[AUDIO_NPU_SPLIT_INDEX:](
            prefix
        ).cpu().numpy()
    wrapper = AudioTail(model).eval()
    output.parent.mkdir(parents=True, exist_ok=True)
    with torch.inference_mode():
        rewritten_reference = wrapper(prefix).cpu().numpy()
        torch.onnx.export(
            wrapper,
            (prefix,),
            output,
            input_names=["prefix"],
            output_names=["audio_chunk"],
            opset_version=18,
            do_constant_folding=True,
            dynamo=False,
        )
    graph = onnx.load(output)
    onnx.checker.check_model(graph)
    session = ort.InferenceSession(str(output), providers=["CPUExecutionProvider"])
    actual = session.run(None, {"prefix": prefix.numpy()})[0]
    rewrite_absolute = np.abs(original_reference - rewritten_reference)
    if not np.allclose(
        original_reference, rewritten_reference, rtol=1e-3, atol=1e-4
    ):
        raise RuntimeError(
            "The 2D audio-tail rewrite changed PyTorch semantics: "
            f"max_abs={float(rewrite_absolute.max())}."
        )
    absolute = np.abs(original_reference - actual)
    max_absolute_error = float(absolute.max())
    mean_absolute_error = float(absolute.mean())
    passed = bool(
        np.allclose(original_reference, actual, rtol=1e-3, atol=1e-4)
    )
    if not passed:
        raise RuntimeError(
            "Audio tail failed PyTorch/CPU ONNX parity: "
            f"max_abs={max_absolute_error}, mean_abs={mean_absolute_error}."
        )
    return {
        "schema_version": 1,
        "source_weights": str(weight_path),
        "source_weights_sha256": weight_hash.hex(),
        "onnx_path": str(output.resolve()),
        "onnx_sha256": file_sha256(output),
        "opset": 18,
        "split": {
            "cpu": ["codebook", "decoder-layers-0-through-12"],
            "npu": ["decoder-layers-13-through-15"],
        },
        "export_rewrite": "single width-1 2D tail with boundary rank conversion",
        "input_name": "prefix",
        "input_shape": [1, 32, 24_000],
        "output_name": "audio_chunk",
        "output_shape": list(actual.shape),
        "cpu_parity": {
            "rewrite_max_absolute_error": float(rewrite_absolute.max()),
            "max_absolute_error": max_absolute_error,
            "mean_absolute_error": mean_absolute_error,
            "passed": passed,
        },
    }


def main() -> None:
    artifacts = generated_artifact_dir()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=artifacts / "audio_tail_fp32.onnx"
    )
    parser.add_argument(
        "--manifest", type=Path, default=artifacts / "audio_tail.manifest.json"
    )
    args = parser.parse_args()
    result = export_tail(args.output.resolve())
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
