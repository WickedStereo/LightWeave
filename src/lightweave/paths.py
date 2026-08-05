"""Portable project and artifact path helpers."""

from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    configured = os.environ.get("LIGHTWEAVE_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def model_manifest_path() -> Path:
    configured = os.environ.get("LIGHTWEAVE_MODEL_MANIFEST")
    if configured:
        return Path(configured).expanduser().resolve()
    return project_root() / "models" / "manifest.json"


def generated_artifact_dir() -> Path:
    configured = os.environ.get("LIGHTWEAVE_ARTIFACT_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return project_root() / "artifacts" / "generated"
