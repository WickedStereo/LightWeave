"""Image reconstruction and transfer metrics."""

from __future__ import annotations

import math

import numpy as np
from PIL import Image


def psnr(reference: Image.Image, reconstructed: Image.Image) -> float:
    reference_array = np.asarray(reference, dtype=np.float64) / 255.0
    reconstructed_array = np.asarray(reconstructed, dtype=np.float64) / 255.0
    if reference_array.shape != reconstructed_array.shape:
        raise ValueError("Metric images must have identical dimensions.")
    mean_square_error = float(np.mean((reference_array - reconstructed_array) ** 2))
    if mean_square_error == 0:
        return math.inf
    return 10.0 * math.log10(1 / mean_square_error)


def array_psnr(reference: np.ndarray, reconstructed: np.ndarray) -> float:
    if reference.shape != reconstructed.shape:
        raise ValueError("Metric arrays must have identical dimensions.")
    difference = reference.astype(np.float64) - reconstructed.astype(np.float64)
    mean_square_error = float(np.mean(difference**2))
    if mean_square_error == 0:
        return math.inf
    return 10.0 * math.log10(1 / mean_square_error)


def ms_ssim(reference: Image.Image, reconstructed: Image.Image) -> float | None:
    if reference.size != reconstructed.size:
        raise ValueError("Metric images must have identical dimensions.")

    # pytorch-msssim performs four fixed downsamplings and requires
    # min(width, height) > (window_size - 1) * 16. Aspect-preserving LightWeave
    # images are often 256 x 144, so select the largest valid odd window rather
    # than silently assuming the default 11-pixel window will fit.
    smaller_side = min(reference.size)
    largest_valid = min(11, ((smaller_side - 1) // 16) + 1)
    win_size = largest_valid if largest_valid % 2 else largest_valid - 1
    if win_size < 3:
        return None

    import torch
    from pytorch_msssim import ms_ssim as torch_ms_ssim

    def tensor(image: Image.Image) -> torch.Tensor:
        array = np.array(image, dtype=np.float32, copy=True) / 255.0
        return torch.from_numpy(array).permute(2, 0, 1).unsqueeze(0)

    with torch.inference_mode():
        value = torch_ms_ssim(
            tensor(reference),
            tensor(reconstructed),
            data_range=1.0,
            size_average=True,
            win_size=win_size,
        )
    return float(value.item())


def transfer_estimates(byte_length: int) -> dict[str, float]:
    bits = byte_length * 8
    return {
        "at_1_kbps_seconds": bits / 1000.0,
        "at_2_kbps_seconds": bits / 2000.0,
    }
