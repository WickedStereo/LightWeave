"""Generate a deterministic, redistributable LightWeave image demo set."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def gradient(path: Path) -> None:
    width, height = 640, 360
    x = np.linspace(0, 1, width, dtype=np.float32)
    y = np.linspace(0, 1, height, dtype=np.float32)[:, None]
    array = np.empty((height, width, 3), dtype=np.uint8)
    array[..., 0] = np.rint(x * 255).astype(np.uint8)
    array[..., 1] = np.rint(y * 255).astype(np.uint8)
    array[..., 2] = np.rint((0.65 * x + 0.35 * y) * 255).astype(np.uint8)
    Image.fromarray(array).save(path)


def color_blocks(path: Path) -> None:
    image = Image.new("RGB", (512, 512), "#0b1020")
    draw = ImageDraw.Draw(image)
    colors = ("#57e3ff", "#966bff", "#ff4d8d", "#ffd166")
    for index, color in enumerate(colors):
        left = 32 + index * 112
        draw.rounded_rectangle(
            (left, 64, left + 96, 448), radius=24, fill=color, outline="white", width=4
        )
    draw.ellipse((176, 176, 336, 336), fill="#0b1020", outline="white", width=8)
    image.save(path)


def optical_rings(path: Path) -> None:
    image = Image.new("RGB", (360, 640), "black")
    draw = ImageDraw.Draw(image)
    center_x, center_y = 180, 320
    for radius in range(170, 10, -20):
        color = (40 + radius, 255 - radius, 220)
        draw.ellipse(
            (
                center_x - radius,
                center_y - radius,
                center_x + radius,
                center_y + radius,
            ),
            outline=color,
            width=10,
        )
    draw.line((40, center_y, 320, center_y), fill="white", width=3)
    draw.line((center_x, 180, center_x, 460), fill="white", width=3)
    image.save(path)


def checkerboard(path: Path) -> None:
    tile = 32
    y, x = np.indices((384, 640))
    board = ((x // tile + y // tile) % 2).astype(np.uint8)
    array = np.empty((384, 640, 3), dtype=np.uint8)
    array[board == 0] = (12, 20, 38)
    array[board == 1] = (79, 227, 255)
    Image.fromarray(array).save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "generated" / "demo-images",
    )
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    generators = {
        "gradient-landscape.png": gradient,
        "color-blocks-square.png": color_blocks,
        "optical-rings-portrait.png": optical_rings,
        "checkerboard-landscape.png": checkerboard,
    }
    for filename, generator in generators.items():
        destination = output_dir / filename
        generator(destination)
        print(destination)


if __name__ == "__main__":
    main()
