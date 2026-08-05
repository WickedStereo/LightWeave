from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

from lightweave.envelope import (
    CodecProfile,
    ColorSpace,
    Envelope,
    ImageMetadata,
    MediaType,
)
from lightweave.errors import ModelMismatchError, PayloadTooLargeError
from lightweave.image import (
    PreparedImage,
    encode_image,
    entropy_decode_image,
    prepare_image,
    write_bytes_atomic,
)
from lightweave.metrics import ms_ssim


def mismatch_metadata() -> ImageMetadata:
    return ImageMetadata(
        model_sha256=hashlib.sha256(b"other model").digest(),
        original_width=256,
        original_height=256,
        content_width=256,
        content_height=256,
        pad_left=0,
        pad_top=0,
        pad_right=0,
        pad_bottom=0,
        latent_channels=192,
        latent_height=16,
        latent_width=16,
        quality=1,
        color_space=ColorSpace.RGB,
    )


def save_image(path: Path, width: int, height: int) -> None:
    x = np.linspace(0, 255, width, dtype=np.uint8)
    y = np.linspace(0, 255, height, dtype=np.uint8)[:, None]
    array = np.empty((height, width, 3), dtype=np.uint8)
    array[..., 0] = x
    array[..., 1] = y
    array[..., 2] = ((x.astype(np.uint16) + y.astype(np.uint16)) // 2).astype(
        np.uint8
    )
    Image.fromarray(array).save(path)


def test_landscape_image_preserves_aspect_ratio(tmp_path: Path) -> None:
    path = tmp_path / "landscape.png"
    save_image(path, 640, 360)
    prepared = prepare_image(path)
    assert (prepared.content_width, prepared.content_height) == (256, 144)
    assert (prepared.pad_left, prepared.pad_top) == (0, 56)
    assert (prepared.pad_right, prepared.pad_bottom) == (0, 56)
    assert tuple(prepared.tensor.shape) == (1, 3, 256, 256)
    assert prepared.visible_reference.size == (256, 144)


def test_portrait_image_preserves_aspect_ratio(tmp_path: Path) -> None:
    path = tmp_path / "portrait.png"
    save_image(path, 300, 600)
    prepared = prepare_image(path)
    assert (prepared.content_width, prepared.content_height) == (128, 256)
    assert (prepared.pad_left, prepared.pad_right) == (64, 64)
    assert (prepared.pad_top, prepared.pad_bottom) == (0, 0)
    assert tuple(prepared.tensor.shape) == (1, 3, 256, 256)


def test_odd_padding_is_symmetric_with_remainder_on_far_edge(tmp_path: Path) -> None:
    path = tmp_path / "odd.png"
    save_image(path, 100, 99)
    prepared = prepare_image(path)
    assert prepared.content_width == 256
    assert prepared.content_height == 253
    assert prepared.pad_top == 1
    assert prepared.pad_bottom == 2


def test_ms_ssim_supports_aspect_preserved_landscape() -> None:
    array = np.zeros((144, 256, 3), dtype=np.uint8)
    image = Image.fromarray(array)
    assert ms_ssim(image, image) == 1.0


def test_oversize_image_is_rejected_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    class Entropy:
        channels = 192

    class Model:
        entropy_bottleneck = Entropy()

        def compress(self, tensor: torch.Tensor) -> dict[str, object]:
            return {"strings": [[bytes(2_000)]], "shape": (16, 16)}

    prepared = PreparedImage(
        tensor=torch.zeros((1, 3, 256, 256)),
        visible_reference=Image.new("RGB", (256, 256)),
        original_width=256,
        original_height=256,
        content_width=256,
        content_height=256,
        pad_left=0,
        pad_top=0,
        pad_right=0,
        pad_bottom=0,
    )
    monkeypatch.setattr(
        "lightweave.image.load_image_model",
        lambda weights_path=None: (Model(), Path("weights"), bytes(32)),
    )
    monkeypatch.setattr("lightweave.image.prepare_image", lambda path: prepared)
    with pytest.raises(PayloadTooLargeError, match="ceiling"):
        encode_image(Path("ignored.png"))


def test_model_mismatch_precedes_entropy_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = Envelope(
        MediaType.IMAGE,
        CodecProfile.BMSHJ2018_FACTORIZED_Q1,
        mismatch_metadata(),
        b"entropy bytes",
    )
    monkeypatch.setattr(
        "lightweave.image.load_image_model",
        lambda weights_path=None: (None, Path("weights"), bytes(32)),
    )
    with pytest.raises(ModelMismatchError, match="different model weights"):
        entropy_decode_image(envelope)


def test_atomic_byte_output_replaces_existing_file(tmp_path: Path) -> None:
    output = tmp_path / "payload.lwv"
    output.write_bytes(b"old")
    write_bytes_atomic(b"new payload", output)
    assert output.read_bytes() == b"new payload"
    assert list(tmp_path.iterdir()) == [output]
