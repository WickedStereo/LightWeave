"""Create the ignored, hash-verified LightWeave UNO Q offline app bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATED = PROJECT_ROOT / "artifacts" / "generated" / "uno_q"
APP_SOURCE = PROJECT_ROOT / "uno_q" / "app"
MODEL_SHA256 = "446d5c7f56d4d5108dc7fb2532cbe45bbf2e78f1778384b04526a8fcd641f5c5"
RUNTIME_FILES = (
    "lightweave-uno-runner",
    "entropy_tables.bin",
    "tiny.ncnn.param",
    "tiny.ncnn.bin",
    "tiny.payload.bin",
    "balanced.ncnn.param",
    "balanced.ncnn.bin",
    "balanced.payload.bin",
    "quality.ncnn.param",
    "quality.ncnn.bin",
    "quality.payload.bin",
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_generated_target(path: Path) -> Path:
    resolved = path.resolve()
    generated_root = (PROJECT_ROOT / "artifacts" / "generated").resolve()
    if resolved == generated_root or generated_root not in resolved.parents:
        raise RuntimeError("UNO Q bundle output must be below artifacts/generated.")
    return resolved


def make_bundle(output_root: Path) -> tuple[Path, Path, dict[str, object]]:
    bundle_root = safe_generated_target(output_root) / "lightweave-uno"
    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    shutil.copytree(APP_SOURCE, bundle_root)
    runtime = bundle_root / "runtime"
    runtime.mkdir(parents=True)
    for name in RUNTIME_FILES:
        source = GENERATED / name
        if not source.is_file():
            raise RuntimeError(
                f"Missing generated UNO Q artifact {source}; run prepare/build first."
            )
        shutil.copy2(source, runtime / name)
    shutil.copy2(
        PROJECT_ROOT / "uno_q" / "native" / "THIRD_PARTY_NOTICES.md",
        bundle_root / "THIRD_PARTY_NOTICES.md",
    )
    shutil.copy2(
        PROJECT_ROOT / "uno_q" / "SBOM.spdx.json",
        bundle_root / "SBOM.spdx.json",
    )
    for executable in (
        bundle_root / "lightweave-uno",
        runtime / "lightweave-uno-runner",
    ):
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)

    source_manifest_path = GENERATED / "bundle.manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    if source_manifest.get("model_sha256") != MODEL_SHA256:
        raise RuntimeError("Generated UNO Q model fingerprint is incompatible.")
    files: dict[str, object] = {}
    for path in sorted(item for item in bundle_root.rglob("*") if item.is_file()):
        relative = path.relative_to(bundle_root).as_posix()
        files[relative] = {"size": path.stat().st_size, "sha256": file_sha256(path)}
    manifest: dict[str, object] = {
        "schema_version": 1,
        "bundle_version": "0.1.0",
        "target": "Arduino UNO Q / Debian ARM64 / Adreno Vulkan",
        "backend": "ncnn-vulkan",
        "strict_no_fallback": True,
        "model_sha256": MODEL_SHA256,
        "runner_sha256": file_sha256(runtime / "lightweave-uno-runner"),
        "entropy_tables_sha256": file_sha256(runtime / "entropy_tables.bin"),
        "source_artifact_manifest_sha256": file_sha256(source_manifest_path),
        "files": files,
    }
    manifest_path = bundle_root / "uno_q.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    archive = safe_generated_target(output_root) / "lightweave-uno-offline.zip"
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(item for item in bundle_root.rglob("*") if item.is_file()):
            output.write(path, Path("lightweave-uno") / path.relative_to(bundle_root))
    return bundle_root, archive, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=GENERATED / "offline-bundle",
    )
    args = parser.parse_args()
    bundle_root, archive, manifest = make_bundle(args.output_root)
    print(
        json.dumps(
            {
                "status": "ok",
                "bundle_root": str(bundle_root),
                "archive": str(archive),
                "archive_sha256": file_sha256(archive),
                "runner_sha256": manifest["runner_sha256"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        raise SystemExit(2) from error
