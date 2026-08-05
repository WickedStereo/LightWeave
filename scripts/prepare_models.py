"""Acquire and verify LightWeave model weights for offline runtime use."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "models" / "manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verified(path: Path, expected: str) -> bool:
    return path.is_file() and sha256(path).lower() == expected.lower()


def prepare_weights(kind: str, output_dir: Path) -> Path:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    record = manifest[kind]["weights"]
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / record["filename"]
    if verified(destination, record["sha256"]):
        print(f"verified existing weights: {destination}")
        return destination

    torch_cache = (
        Path.home() / ".cache" / "torch" / "hub" / "checkpoints" / record["filename"]
    )
    if verified(torch_cache, record["sha256"]):
        shutil.copyfile(torch_cache, destination)
    else:
        with tempfile.NamedTemporaryFile(
            prefix="lightweave-weights-", suffix=".download", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        try:
            print(f"downloading {record['url']}")
            urllib.request.urlretrieve(record["url"], temporary_path)
            if not verified(temporary_path, record["sha256"]):
                raise RuntimeError(
                    "Downloaded model weights failed SHA-256 verification."
                )
            shutil.copyfile(temporary_path, destination)
        finally:
            temporary_path.unlink(missing_ok=True)

    if not verified(destination, record["sha256"]):
        destination.unlink(missing_ok=True)
        raise RuntimeError("Prepared model weights failed final SHA-256 verification.")
    print(f"prepared weights: {destination}")
    print(f"sha256={record['sha256']}")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "models" / "weights",
    )
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    for kind in ("image", "audio"):
        prepare_weights(kind, output_dir)


if __name__ == "__main__":
    main()
