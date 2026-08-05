from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from lightweave.errors import ModelMismatchError
from lightweave.npu import _verify_local_decoder


def test_decoder_manifest_is_portable_between_snapdragon_hosts(
    tmp_path: Path,
) -> None:
    model = tmp_path / "raw_image_decoder_qdq.onnx"
    model.write_bytes(b"portable generated graph")
    graph_hash = hashlib.sha256(model.read_bytes()).hexdigest()
    source_hash = hashlib.sha256(b"pinned weights").digest()
    manifest = tmp_path / "raw_image_decoder.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "source_weights_sha256": source_hash.hex(),
                "quantized_onnx_path": "C:/different-host/artifacts/model.onnx",
                "quantized_onnx_sha256": graph_hash,
            }
        ),
        encoding="utf-8",
    )
    _verify_local_decoder(model, source_hash, manifest)


def test_decoder_manifest_rejects_unrecorded_graph_hash(tmp_path: Path) -> None:
    model = tmp_path / "decoder.onnx"
    model.write_bytes(b"wrong graph")
    source_hash = bytes(32)
    manifest = tmp_path / "decoder.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "source_weights_sha256": source_hash.hex(),
                "quantized_onnx_sha256": hashlib.sha256(b"expected").hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ModelMismatchError, match="does not match"):
        _verify_local_decoder(model, source_hash, manifest)
