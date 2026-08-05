"""Run the documented LightWeave image acceptance set and write a report."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightweave.image import encode_image  # noqa: E402
from lightweave.metrics import psnr  # noqa: E402
from lightweave.service import decode_image_bytes, roundtrip_image  # noqa: E402


def evaluate(
    manifest_path: Path, image_dir: Path, output_dir: Path, backend: str
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    thresholds = manifest["acceptance"]
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for filename in manifest["acceptance_images"]:
        input_path = image_dir / filename
        if not input_path.is_file():
            raise FileNotFoundError(
                f"{input_path} is missing; run scripts/generate_demo_images.py."
            )
        item_dir = output_dir / Path(filename).stem
        item_dir.mkdir(parents=True, exist_ok=True)
        result = roundtrip_image(
            input_path,
            backend=backend,  # type: ignore[arg-type]
            payload_path=item_dir / "payload.lwv",
            output_path=item_dir / "reconstructed.png",
        )
        if backend == "qnn":
            cpu = decode_image_bytes(
                (item_dir / "payload.lwv").read_bytes(),
                backend="cpu",
                output_path=item_dir / "cpu-reference.png",
            )
            with Image.open(item_dir / "reconstructed.png") as source:
                npu_image = source.convert("RGB")
            result["cpu_npu_psnr_db"] = psnr(cpu.visible_image, npu_image)
        result["filename"] = filename
        results.append(result)

    stress_results = []
    for case in manifest.get("analysis_images", []):
        encoded = encode_image(image_dir / case["filename"], allow_oversize=True)
        stress_results.append(
            {
                **case,
                "envelope_bytes": len(encoded.envelope_bytes),
                "default_budget_rejected": len(encoded.envelope_bytes)
                > thresholds["max_complete_envelope_bytes"],
            }
        )

    mean_psnr = statistics.fmean(item["psnr_db"] for item in results)
    ms_ssim_values = [
        item["ms_ssim"] for item in results if item["ms_ssim"] is not None
    ]
    mean_ms_ssim = statistics.fmean(ms_ssim_values)
    checks = {
        "payload_budget": all(
            item["envelope_bytes"] <= thresholds["max_complete_envelope_bytes"]
            for item in results
        ),
        "mean_psnr": mean_psnr >= thresholds["minimum_average_psnr_db"],
        "mean_ms_ssim": mean_ms_ssim >= thresholds["minimum_average_ms_ssim"],
        "transfer_1kbps": all(
            item["at_1_kbps_seconds"] <= 16.384 for item in results
        ),
        "transfer_2kbps": all(
            item["at_2_kbps_seconds"] <= 8.192 for item in results
        ),
    }
    if backend == "qnn":
        checks["strict_npu"] = all(
            item["npu_evidence"]["strict_no_fallback"]
            and item["npu_evidence"]["profile_cpu_node_count"] == 0
            for item in results
        )
        checks["cpu_npu_parity"] = all(
            item["cpu_npu_psnr_db"] >= 35.0 for item in results
        )

    return {
        "schema_version": 1,
        "backend": backend,
        "thresholds": thresholds,
        "summary": {
            "image_count": len(results),
            "mean_psnr_db": mean_psnr,
            "mean_ms_ssim": mean_ms_ssim,
            "maximum_envelope_bytes": max(
                item["envelope_bytes"] for item in results
            ),
            "passed": all(checks.values()),
        },
        "checks": checks,
        "images": results,
        "analysis_images": stress_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("cpu", "qnn"), default="qnn")
    parser.add_argument(
        "--manifest", type=Path, default=PROJECT_ROOT / "data/demo_manifest.json"
    )
    parser.add_argument(
        "--image-dir",
        type=Path,
        default=PROJECT_ROOT / "data/generated/demo-images",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "reports/generated/image-acceptance",
    )
    args = parser.parse_args()
    report = evaluate(
        args.manifest.resolve(),
        args.image_dir.resolve(),
        args.output_dir.resolve(),
        args.backend,
    )
    report_path = args.output_dir / f"{args.backend}-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["summary"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
