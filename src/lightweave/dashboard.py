"""Offline localhost dashboard for LightWeave image and audio workflows."""

from __future__ import annotations

import base64
import io
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError

from .audio import resolve_audio_weights, roundtrip_audio
from .audio_npu import default_audio_tail_model
from .errors import LightWeaveError
from .image import resolve_image_weights
from .npu import default_arm64_python, default_decoder_model
from .service import roundtrip_image

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
STATIC_DIR = Path(__file__).with_name("static")


def _package_version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def _png_data_url(path: Path, *, correct_orientation: bool = False) -> str:
    with Image.open(path) as source:
        image = (
            ImageOps.exif_transpose(source)
            if correct_orientation
            else source.copy()
        )
        image = image.convert("RGB")
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    encoded = base64.b64encode(stream.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _runtime_status() -> dict[str, object]:
    try:
        weights = resolve_image_weights()
        weights_ready = True
    except (FileNotFoundError, LightWeaveError):
        weights = None
        weights_ready = False
    arm64_python = default_arm64_python()
    decoder = default_decoder_model()
    try:
        audio_weights = resolve_audio_weights()
        audio_weights_ready = True
    except (FileNotFoundError, LightWeaveError):
        audio_weights = None
        audio_weights_ready = False
    audio_tail = default_audio_tail_model()
    return {
        "offline": True,
        "bind_host": "127.0.0.1",
        "weights_ready": weights_ready,
        "weights_path": str(weights) if weights else None,
        "decoder_ready": decoder.is_file(),
        "decoder_path": str(decoder),
        "arm64_worker_ready": arm64_python.is_file(),
        "arm64_python": str(arm64_python),
        "audio_weights_ready": audio_weights_ready,
        "audio_weights_path": str(audio_weights) if audio_weights else None,
        "audio_tail_ready": audio_tail.is_file(),
        "audio_tail_path": str(audio_tail),
        "versions": {
            "lightweave": _package_version("lightweave"),
            "compressai": _package_version("compressai"),
            "encodec": _package_version("encodec"),
            "onnxruntime": _package_version("onnxruntime"),
        },
    }


def create_app() -> FastAPI:
    app = FastAPI(
        title="LightWeave",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/status")
    def status() -> dict[str, object]:
        return _runtime_status()

    @app.post("/api/image/roundtrip")
    def image_roundtrip(
        file: Annotated[UploadFile, File()],
        backend: Annotated[Literal["qnn", "cpu"], Form()] = "qnn",
        allow_oversize: Annotated[bool, Form()] = False,
    ) -> dict[str, object]:
        value = file.file.read(MAX_UPLOAD_BYTES + 1)
        if len(value) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Image upload exceeds 20 MiB.")
        if not value:
            raise HTTPException(status_code=400, detail="The uploaded image is empty.")

        try:
            with tempfile.TemporaryDirectory(prefix="lightweave-dashboard-") as temp:
                work_dir = Path(temp)
                input_path = work_dir / "input-image"
                input_path.write_bytes(value)
                payload_path = work_dir / "payload.lwv"
                output_path = work_dir / "reconstructed.png"
                result = roundtrip_image(
                    input_path,
                    backend=backend,
                    payload_path=payload_path,
                    output_path=output_path,
                    allow_oversize=allow_oversize,
                )
                return {
                    "result": result,
                    "input_image": _png_data_url(
                        input_path, correct_orientation=True
                    ),
                    "reconstructed_image": _png_data_url(output_path),
                }
        except (UnidentifiedImageError, OSError) as exc:
            raise HTTPException(
                status_code=400, detail="The upload is not a supported image."
            ) from exc
        except LightWeaveError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/audio/roundtrip")
    def audio_roundtrip(
        file: Annotated[UploadFile, File()],
        backend: Annotated[Literal["hybrid-qnn", "cpu"], Form()] = "hybrid-qnn",
    ) -> dict[str, object]:
        value = file.file.read(MAX_UPLOAD_BYTES + 1)
        if len(value) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Audio upload exceeds 20 MiB.")
        if not value:
            raise HTTPException(status_code=400, detail="The uploaded WAV is empty.")
        try:
            with tempfile.TemporaryDirectory(
                prefix="lightweave-audio-dashboard-"
            ) as temp:
                work_dir = Path(temp)
                input_path = work_dir / "input.wav"
                input_path.write_bytes(value)
                output_path = work_dir / "reconstructed.wav"
                result = roundtrip_audio(
                    input_path,
                    backend=backend,
                    payload_path=work_dir / "payload.lwv",
                    output_path=output_path,
                )
                encoded = base64.b64encode(output_path.read_bytes()).decode("ascii")
                return {
                    "result": result,
                    "reconstructed_audio": f"data:audio/wav;base64,{encoded}",
                }
        except (FileNotFoundError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (LightWeaveError, ValueError, OSError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app


app = create_app()


def run_dashboard(*, port: int = 8765) -> None:
    import uvicorn

    if not 1 <= port <= 65535:
        raise ValueError("Dashboard port must be between 1 and 65535.")
    uvicorn.run(app, host="127.0.0.1", port=port, access_log=False)
