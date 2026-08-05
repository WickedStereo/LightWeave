"""Offline localhost dashboard for LightWeave image and audio workflows."""

from __future__ import annotations

import base64
import io
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError

from .audio import resolve_audio_weights, roundtrip_audio
from .audio_npu import default_audio_tail_model
from .errors import LightWeaveError
from .image import resolve_image_weights
from .metrics import ms_ssim, psnr, transfer_estimates
from .npu import (
    default_arm64_python,
    default_decoder_model,
    default_raw_decoder_model,
)
from .raw import (
    RAW_AUDIO_CHUNK_BYTES,
    RAW_IMAGE_MAX_BYTES,
    decode_raw_audio,
    decode_raw_image,
    encode_raw_audio,
    encode_raw_image,
)
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


def _image_data_url(image: Image.Image) -> str:
    stream = io.BytesIO()
    image.convert("RGB").save(stream, format="PNG")
    encoded = base64.b64encode(stream.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _audio_data_url(value: bytes) -> str:
    return "data:audio/wav;base64," + base64.b64encode(value).decode("ascii")


def _runtime_status() -> dict[str, object]:
    try:
        weights = resolve_image_weights()
        weights_ready = True
    except (FileNotFoundError, LightWeaveError):
        weights = None
        weights_ready = False
    arm64_python = default_arm64_python()
    decoder = default_decoder_model()
    raw_decoder = default_raw_decoder_model()
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
        "raw_decoder_ready": raw_decoder.is_file(),
        "raw_decoder_path": str(raw_decoder),
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
    def index() -> RedirectResponse:
        return RedirectResponse("/transmit", status_code=307)

    @app.get("/transmit", include_in_schema=False)
    def transmit_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "transmit.html")

    @app.get("/receive", include_in_schema=False)
    def receive_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "receive.html")

    @app.get("/loopback", include_in_schema=False)
    def loopback_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/status")
    def status() -> dict[str, object]:
        return _runtime_status()

    @app.post("/api/transmit/image")
    def transmit_image(
        file: Annotated[UploadFile, File()],
    ) -> dict[str, object]:
        value = file.file.read(MAX_UPLOAD_BYTES + 1)
        if len(value) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Image upload exceeds 20 MiB.")
        if not value:
            raise HTTPException(status_code=400, detail="The uploaded image is empty.")
        try:
            with tempfile.TemporaryDirectory(prefix="lightweave-raw-image-tx-") as temp:
                input_path = Path(temp) / "input-image"
                input_path.write_bytes(value)
                encoded = encode_raw_image(input_path)
                raw_bytes = len(encoded.payload)
                return {
                    "preset_code": encoded.preset_code,
                    "payload_base64": base64.b64encode(encoded.payload).decode("ascii"),
                    "raw_bytes": raw_bytes,
                    "maximum_bytes": RAW_IMAGE_MAX_BYTES,
                    "within_budget": raw_bytes <= RAW_IMAGE_MAX_BYTES,
                    "effective_detail": encoded.effective_detail,
                    "fallback": encoded.fallback,
                    "bits_per_pixel": raw_bytes * 8 / (64 * 64),
                    "encode_seconds": encoded.encode_seconds,
                    **transfer_estimates(raw_bytes),
                    "input_image": _image_data_url(encoded.original_preview),
                    "encoded_reference": _image_data_url(encoded.reference),
                    "warning": (
                        "Raw mode contains no integrity or model-negotiation fields."
                    ),
                }
        except (UnidentifiedImageError, OSError) as exc:
            raise HTTPException(
                status_code=400, detail="The upload is not a supported image."
            ) from exc
        except (LightWeaveError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (FileNotFoundError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/transmit/audio")
    def transmit_audio(
        file: Annotated[UploadFile, File()],
    ) -> dict[str, object]:
        value = file.file.read(MAX_UPLOAD_BYTES + 1)
        if len(value) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Audio upload exceeds 20 MiB.")
        if not value:
            raise HTTPException(status_code=400, detail="The uploaded WAV is empty.")
        try:
            with tempfile.TemporaryDirectory(prefix="lightweave-raw-audio-tx-") as temp:
                input_path = Path(temp) / "input.wav"
                input_path.write_bytes(value)
                encoded = encode_raw_audio(input_path)
                raw_bytes = len(encoded.payload)
                duration = encoded.original_samples / 24_000
                return {
                    "preset_code": encoded.preset_code,
                    "payload_base64": base64.b64encode(encoded.payload).decode("ascii"),
                    "raw_bytes": raw_bytes,
                    "chunk_count": encoded.chunk_count,
                    "bytes_per_chunk": RAW_AUDIO_CHUNK_BYTES,
                    "original_samples": encoded.original_samples,
                    "duration_seconds": duration,
                    "code_payload_bps": raw_bytes * 8 / duration,
                    "encode_seconds": encoded.encode_seconds,
                    **transfer_estimates(raw_bytes),
                    "input_audio": _audio_data_url(value),
                    "warning": (
                        "Raw mode contains no integrity or model-negotiation fields."
                    ),
                }
        except (LightWeaveError, ValueError, OSError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (FileNotFoundError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/receive/image")
    def receive_image(
        file: Annotated[UploadFile, File()],
        preset_code: Annotated[str, Form()],
        backend: Annotated[Literal["qnn", "cpu"], Form()] = "qnn",
        reference: Annotated[UploadFile | None, File()] = None,
    ) -> dict[str, object]:
        payload = file.file.read(RAW_IMAGE_MAX_BYTES + 2)
        if not payload:
            raise HTTPException(status_code=400, detail="Raw image payload is empty.")
        reference_value = (
            reference.file.read(MAX_UPLOAD_BYTES + 1) if reference else None
        )
        try:
            with tempfile.TemporaryDirectory(prefix="lightweave-raw-image-rx-") as temp:
                output_path = Path(temp) / "reconstructed.png"
                decoded = decode_raw_image(
                    payload,
                    preset_code=preset_code,
                    backend=backend,
                    output_path=output_path,
                )
                quality: dict[str, object] = {}
                if reference_value:
                    with Image.open(io.BytesIO(reference_value)) as source:
                        reference_image = source.convert("RGB")
                    if reference_image.size != (64, 64):
                        raise ValueError(
                            "Verification reference must be exactly 64×64."
                        )
                    quality = {
                        "psnr_db": psnr(reference_image, decoded.image),
                        "ms_ssim": ms_ssim(reference_image, decoded.image),
                    }
                return {
                    "preset_code": preset_code,
                    "raw_bytes": len(payload),
                    "output_width": decoded.image.width,
                    "output_height": decoded.image.height,
                    "backend": decoded.backend,
                    "entropy_decode_seconds": decoded.entropy_decode_seconds,
                    "reconstruction_seconds": decoded.reconstruction_seconds,
                    "npu_evidence": decoded.evidence,
                    "reconstructed_image": _image_data_url(decoded.image),
                    **quality,
                }
        except (UnidentifiedImageError, OSError) as exc:
            raise HTTPException(
                status_code=400, detail="The verification reference is not an image."
            ) from exc
        except (LightWeaveError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (FileNotFoundError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/receive/audio")
    def receive_audio(
        file: Annotated[UploadFile, File()],
        preset_code: Annotated[str, Form()],
        backend: Annotated[Literal["hybrid-qnn", "cpu"], Form()] = "hybrid-qnn",
    ) -> dict[str, object]:
        payload = file.file.read(MAX_UPLOAD_BYTES + 1)
        if len(payload) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Raw audio exceeds 20 MiB.")
        if not payload:
            raise HTTPException(status_code=400, detail="Raw audio payload is empty.")
        try:
            with tempfile.TemporaryDirectory(prefix="lightweave-raw-audio-rx-") as temp:
                output_path = Path(temp) / "reconstructed.wav"
                decoded = decode_raw_audio(
                    payload,
                    preset_code=preset_code,
                    backend=backend,
                    output_path=output_path,
                )
                return {
                    "preset_code": preset_code,
                    "raw_bytes": len(payload),
                    "chunk_count": len(payload) // RAW_AUDIO_CHUNK_BYTES,
                    "restored_samples": int(decoded.waveform.shape[-1]),
                    "backend": decoded.backend,
                    "codebook_decode_seconds": decoded.codebook_seconds,
                    "cpu_prefix_seconds": decoded.cpu_prefix_seconds,
                    "reconstruction_seconds": decoded.reconstruction_seconds,
                    "execution_evidence": decoded.evidence,
                    "reconstructed_audio": _audio_data_url(output_path.read_bytes()),
                }
        except (LightWeaveError, ValueError, OSError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (FileNotFoundError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

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
