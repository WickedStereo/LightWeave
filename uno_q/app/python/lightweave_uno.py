"""Native LightWeave image receiver CLI and local HTTP service for UNO Q."""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import json
import os
import platform
import re
import shutil
import statistics
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

try:
    import fcntl
except ImportError:  # pragma: no cover - Linux target module
    fcntl = None

try:
    import resource
except ImportError:  # pragma: no cover - Linux target module
    resource = None

MODEL_SHA256 = "446d5c7f56d4d5108dc7fb2532cbe45bbf2e78f1778384b04526a8fcd641f5c5"
MAX_REQUEST_BYTES = 2_048
APP_ROOT = Path(
    os.environ.get("LIGHTWEAVE_UNO_HOME", Path(__file__).resolve().parents[1])
).resolve()
RUNTIME_ROOT = Path(
    os.environ.get("LIGHTWEAVE_UNO_RUNTIME", APP_ROOT / "runtime")
).resolve()
MANIFEST_PATH = Path(
    os.environ.get("LIGHTWEAVE_UNO_MANIFEST", APP_ROOT / "uno_q.manifest.json")
).resolve()
ASSET_ROOT = APP_ROOT / "assets"
ACCELERATOR_COOLDOWN_SECONDS = 1.0
_ACCELERATOR_LOCK = threading.Lock()
_LAST_ACCELERATOR_FINISH = 0.0


@dataclass(frozen=True, slots=True)
class Preset:
    code: str
    stem: str
    output_size: int
    maximum_bytes: int

    @property
    def parameter_path(self) -> Path:
        return RUNTIME_ROOT / f"{self.stem}.ncnn.param"

    @property
    def weights_path(self) -> Path:
        return RUNTIME_ROOT / f"{self.stem}.ncnn.bin"

    @property
    def fixture_path(self) -> Path:
        return RUNTIME_ROOT / f"{self.stem}.payload.bin"


PRESETS = (
    Preset("I64-Q1-B128", "tiny", 64, 128),
    Preset("I128-Q1-B768", "balanced", 128, 768),
    Preset("I256-Q1-B2048", "quality", 256, 2_048),
)
PRESET_BY_CODE = {preset.code: preset for preset in PRESETS}


class UnoQError(RuntimeError):
    """Safe error surfaced by the CLI and local API."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _preset(code: str) -> Preset:
    try:
        return PRESET_BY_CODE[code]
    except KeyError as exc:
        raise UnoQError(f"Unsupported raw image preset: {code}.") from exc


def _load_manifest() -> dict[str, Any]:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UnoQError(
            f"Invalid or missing bundle manifest: {MANIFEST_PATH}."
        ) from exc
    if manifest.get("schema_version") != 1:
        raise UnoQError("Unsupported UNO Q bundle manifest version.")
    if manifest.get("model_sha256") != MODEL_SHA256:
        raise UnoQError("UNO Q bundle model fingerprint is incompatible.")
    if not isinstance(manifest.get("files"), dict):
        raise UnoQError("UNO Q bundle manifest has no file registry.")
    return manifest


def _verify_artifact(path: Path, manifest: dict[str, Any]) -> None:
    try:
        relative = path.relative_to(APP_ROOT).as_posix()
    except ValueError as exc:
        raise UnoQError(f"Artifact is outside the installed app: {path}.") from exc
    record = manifest["files"].get(relative)
    if not isinstance(record, dict):
        raise UnoQError(f"Artifact is not registered in the bundle: {relative}.")
    try:
        expected_size = int(record["size"])
        expected_hash = str(record["sha256"])
    except (KeyError, TypeError, ValueError) as exc:
        raise UnoQError(f"Invalid manifest record for {relative}.") from exc
    if not path.is_file() or path.stat().st_size != expected_size:
        raise UnoQError(f"Artifact size check failed: {relative}.")
    if _sha256(path) != expected_hash:
        raise UnoQError(f"Artifact hash check failed: {relative}.")


def _required_paths(preset: Preset) -> tuple[Path, ...]:
    return (
        RUNTIME_ROOT / "lightweave-uno-runner",
        RUNTIME_ROOT / "entropy_tables.bin",
        preset.parameter_path,
        preset.weights_path,
    )


def validate_installation(preset: Preset | None = None) -> dict[str, Any]:
    manifest = _load_manifest()
    selected = PRESETS if preset is None else (preset,)
    paths = {path for item in selected for path in _required_paths(item)}
    for path in sorted(paths):
        _verify_artifact(path, manifest)
    return manifest


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind)
    checksum = zlib.crc32(data, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def ppm_to_png(data: bytes) -> tuple[bytes, int, int]:
    match = re.match(
        rb"P6[ \t\r\n]+([1-9][0-9]*)[ \t\r\n]+([1-9][0-9]*)"
        rb"[ \t\r\n]+255[ \t\r\n]",
        data,
    )
    if match is None:
        raise UnoQError("Native runner returned an invalid PPM image.")
    width, height = (int(value) for value in match.groups())
    pixels = data[match.end() :]
    if width > 256 or height > 256 or len(pixels) != width * height * 3:
        raise UnoQError("Native runner returned an invalid PPM payload length.")
    rows = b"".join(
        b"\x00" + pixels[offset : offset + width * 3]
        for offset in range(0, len(pixels), width * 3)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(rows, level=9))
        + _png_chunk(b"IEND", b"")
    )
    return png, width, height


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(temporary_name)
        raise


def _run_native(
    command: list[str], environment: dict[str, str]
) -> tuple[subprocess.CompletedProcess[str], float, int | None, int | None]:
    global _LAST_ACCELERATOR_FINISH  # noqa: PLW0603
    with _ACCELERATOR_LOCK:
        lock_stream = None
        try:
            shared_finish = 0.0
            if fcntl is not None:
                lock_path = RUNTIME_ROOT / ".accelerator.lock"
                lock_stream = lock_path.open("a+b")
                fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
                lock_stream.seek(0)
                with contextlib.suppress(ValueError):
                    shared_finish = float(lock_stream.read().decode("ascii") or "0")
            remaining = ACCELERATOR_COOLDOWN_SECONDS - min(
                time.perf_counter() - _LAST_ACCELERATOR_FINISH,
                time.time() - shared_finish,
            )
            if remaining > 0:
                time.sleep(remaining)
            started = time.perf_counter()
            child_peak_before = (
                resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
                if resource is not None
                else None
            )
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    env=environment,
                    text=True,
                    timeout=90,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise UnoQError(
                    "Native accelerator runner could not be executed."
                ) from exc
            total_seconds = time.perf_counter() - started
            child_peak_after = (
                resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
                if resource is not None
                else None
            )
        finally:
            _LAST_ACCELERATOR_FINISH = time.perf_counter()
            if lock_stream is not None:
                lock_stream.seek(0)
                lock_stream.truncate()
                lock_stream.write(str(time.time()).encode("ascii"))
                lock_stream.flush()
                os.fsync(lock_stream.fileno())
                fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)
                lock_stream.close()
    return completed, total_seconds, child_peak_before, child_peak_after


def decode_payload(payload: bytes, preset_code: str) -> tuple[bytes, dict[str, Any]]:
    preset = _preset(preset_code)
    if not payload:
        raise UnoQError("Raw image payload is empty.")
    if len(payload) > preset.maximum_bytes:
        raise UnoQError(
            f"Payload is {len(payload)} bytes; {preset.code} allows at most "
            f"{preset.maximum_bytes}."
        )
    manifest = validate_installation(preset)
    runner = RUNTIME_ROOT / "lightweave-uno-runner"
    tables = RUNTIME_ROOT / "entropy_tables.bin"
    with tempfile.TemporaryDirectory(prefix="lightweave-uno-") as temporary:
        work = Path(temporary)
        payload_path = work / "payload.bin"
        ppm_path = work / "reconstruction.ppm"
        payload_path.write_bytes(payload)
        command = [
            str(runner),
            "decode",
            "--preset",
            preset.code,
            "--payload",
            str(payload_path),
            "--tables",
            str(tables),
            "--model-param",
            str(preset.parameter_path),
            "--model-bin",
            str(preset.weights_path),
            "--output",
            str(ppm_path),
        ]
        environment = os.environ.copy()
        vulkan_runtime = RUNTIME_ROOT / "vulkan"
        icd_path = vulkan_runtime / "freedreno_icd.json"
        if vulkan_runtime.is_dir() and icd_path.is_file():
            existing_library_path = environment.get("LD_LIBRARY_PATH", "")
            environment["LD_LIBRARY_PATH"] = str(vulkan_runtime) + (
                f":{existing_library_path}" if existing_library_path else ""
            )
            environment["VK_ICD_FILENAMES"] = str(icd_path)
        completed, total_seconds, child_peak_before, child_peak_after = _run_native(
            command, environment
        )
        output_lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if completed.returncode != 0 or not output_lines:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise UnoQError(f"Native accelerator reconstruction failed: {detail[:500]}")
        try:
            evidence = json.loads(output_lines[-1])
        except json.JSONDecodeError as exc:
            raise UnoQError("Native accelerator evidence is not valid JSON.") from exc
        if (
            evidence.get("status") != "ok"
            or evidence.get("backend") != "ncnn-vulkan"
            or evidence.get("strict_no_fallback") is not True
            or "Adreno" not in str(evidence.get("device", ""))
            or int(evidence.get("compute_layers", 0)) <= 0
            or evidence.get("model_sha256") != MODEL_SHA256
        ):
            raise UnoQError("Native runner did not prove strict Adreno reconstruction.")
        try:
            png, width, height = ppm_to_png(ppm_path.read_bytes())
        except OSError as exc:
            raise UnoQError(
                "Native runner did not create its reconstructed image."
            ) from exc
    if width != preset.output_size or height != preset.output_size:
        raise UnoQError("Native runner returned the wrong reconstruction dimensions.")
    evidence.update(
        {
            "preset_code": preset.code,
            "raw_bytes": len(payload),
            "output_width": width,
            "output_height": height,
            "total_seconds": total_seconds,
            "bundle_version": manifest.get("bundle_version", "unknown"),
            "peak_child_rss_kib": child_peak_after,
            "previous_peak_child_rss_kib": child_peak_before,
        }
    )
    return png, evidence


def doctor() -> dict[str, Any]:
    issues: list[str] = []
    if platform.machine().lower() not in {"aarch64", "arm64"}:
        issues.append(f"unsupported architecture: {platform.machine()}")
    render_node = Path("/dev/dri/renderD128")
    if not render_node.exists():
        issues.append("missing /dev/dri/renderD128")
    try:
        manifest = validate_installation()
    except UnoQError as exc:
        issues.append(str(exc))
        manifest = {}
    vulkan = shutil.which("vulkaninfo")
    gpu_summary = "unavailable"
    if vulkan:
        completed = subprocess.run(
            [vulkan, "--summary"], capture_output=True, text=True, timeout=15
        )
        combined = completed.stdout + completed.stderr
        match = re.search(r"deviceName\s*=\s*(.+)", combined)
        if match:
            gpu_summary = match.group(1).strip()
        if completed.returncode != 0 or "Adreno" not in combined:
            issues.append("vulkaninfo did not identify the Adreno GPU")
    else:
        probe = PRESETS[0]
        try:
            _, evidence = decode_payload(probe.fixture_path.read_bytes(), probe.code)
            gpu_summary = str(evidence["device"])
        except (OSError, UnoQError, ValueError) as exc:
            issues.append(f"strict Adreno probe failed: {exc}")
    return {
        "status": "ok" if not issues else "error",
        "device": "Arduino UNO Q",
        "os": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "render_node": str(render_node),
        "gpu": gpu_summary,
        "backend": "ncnn-vulkan",
        "strict_no_fallback": True,
        "model_sha256": manifest.get("model_sha256"),
        "bundle_version": manifest.get("bundle_version"),
        "issues": issues,
    }


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "LightWeaveUNO/0.1"

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'")
        self.end_headers()
        self.wfile.write(data)

    def _asset(self, name: str, content_type: str) -> None:
        path = ASSET_ROOT / name
        try:
            data = path.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; script-src 'self'; "
            "style-src 'self'; connect-src 'self'",
        )
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._asset("index.html", "text/html; charset=utf-8")
        elif path == "/app.js":
            self._asset("app.js", "text/javascript; charset=utf-8")
        elif path == "/styles.css":
            self._asset("styles.css", "text/css; charset=utf-8")
        elif path == "/api/status":
            result = doctor()
            status = (
                HTTPStatus.OK
                if result["status"] == "ok"
                else HTTPStatus.SERVICE_UNAVAILABLE
            )
            self._json(status, result)
        elif path == "/api/presets":
            self._json(
                HTTPStatus.OK,
                {
                    "presets": [
                        {
                            "code": item.code,
                            "output_size": item.output_size,
                            "maximum_bytes": item.maximum_bytes,
                        }
                        for item in PRESETS
                    ]
                },
            )
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/receive/image":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if self.headers.get_content_type() != "application/octet-stream":
            self._json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                {"status": "error", "message": "Expected application/octet-stream."},
            )
            return
        preset_values = parse_qs(parsed.query).get("preset", [])
        preset_code = preset_values[0] if len(preset_values) == 1 else ""
        try:
            preset = _preset(preset_code)
            content_length = int(self.headers.get("Content-Length", "-1"))
            if content_length < 0 or content_length > min(
                preset.maximum_bytes, MAX_REQUEST_BYTES
            ):
                raise UnoQError("Invalid payload Content-Length.")
            payload = self.rfile.read(content_length)
            if len(payload) != content_length:
                raise UnoQError("Truncated HTTP request body.")
            png, evidence = decode_payload(payload, preset.code)
            self._json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "png_base64": base64.b64encode(png).decode("ascii"),
                    "metrics": evidence,
                },
            )
        except (UnoQError, ValueError) as exc:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"status": "error", "message": str(exc)},
            )

    def log_message(self, format_string: str, *args: object) -> None:
        print(f"{self.client_address[0]} - {format_string % args}", file=sys.stderr)


def _print_json(value: dict[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _decode_command(args: argparse.Namespace) -> int:
    payload = args.payload.read_bytes()
    png, evidence = decode_payload(payload, args.preset)
    _atomic_write(args.output.resolve(), png)
    _print_json({"status": "ok", "output": str(args.output.resolve()), **evidence})
    return 0


def _benchmark_command(args: argparse.Namespace) -> int:
    if not 1 <= args.runs <= 20:
        raise UnoQError("Benchmark runs must be between 1 and 20.")
    selected = PRESETS if args.preset == "all" else (_preset(args.preset),)
    results = []
    for preset in selected:
        if not preset.fixture_path.is_file():
            raise UnoQError(f"Benchmark fixture is missing for {preset.code}.")
        payload = preset.fixture_path.read_bytes()
        observations = []
        for _ in range(args.runs):
            _, evidence = decode_payload(payload, preset.code)
            observations.append(evidence)
        inference = [float(item["inference_seconds"]) for item in observations]
        total = [float(item["total_seconds"]) for item in observations]
        p95_index = 94
        inference_p95 = (
            statistics.quantiles(inference, n=100, method="inclusive")[p95_index]
            if len(inference) > 1
            else inference[0]
        )
        total_p95 = (
            statistics.quantiles(total, n=100, method="inclusive")[p95_index]
            if len(total) > 1
            else total[0]
        )
        results.append(
            {
                "preset_code": preset.code,
                "runs": args.runs,
                "raw_bytes": len(payload),
                "first_run_seconds": total[0],
                "median_inference_seconds": statistics.median(inference),
                "p95_inference_seconds": inference_p95,
                "median_total_seconds": statistics.median(total),
                "p95_total_seconds": total_p95,
                "peak_child_rss_kib": max(
                    int(item.get("peak_child_rss_kib") or 0)
                    for item in observations
                ),
                "backend": observations[-1]["backend"],
                "device": observations[-1]["device"],
                "strict_no_fallback": observations[-1]["strict_no_fallback"],
                "compute_layers": observations[-1]["compute_layers"],
            }
        )
    disk = shutil.disk_usage(APP_ROOT)
    bundle_bytes = sum(
        path.stat().st_size for path in APP_ROOT.rglob("*") if path.is_file()
    )
    _print_json(
        {
            "status": "ok",
            "results": results,
            "bundle_bytes": bundle_bytes,
            "disk_free_bytes": disk.free,
            "disk_total_bytes": disk.total,
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lightweave-uno")
    subparsers = parser.add_subparsers(dest="command", required=True)
    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--json", action="store_true")

    image_parser = subparsers.add_parser("image")
    image_subparsers = image_parser.add_subparsers(dest="image_command", required=True)
    decode_parser = image_subparsers.add_parser("decode")
    decode_parser.add_argument("payload", type=Path)
    decode_parser.add_argument("--preset", required=True, choices=tuple(PRESET_BY_CODE))
    decode_parser.add_argument("--output", "-o", type=Path, required=True)
    decode_parser.add_argument("--require-accelerator", action="store_true")

    benchmark_parser = subparsers.add_parser("benchmark")
    benchmark_parser.add_argument(
        "--preset", default="all", choices=("all", *PRESET_BY_CODE)
    )
    benchmark_parser.add_argument("--runs", type=int, default=5)
    benchmark_parser.add_argument("--json", action="store_true")

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=7000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            result = doctor()
            _print_json(result)
            return 0 if result["status"] == "ok" else 2
        if args.command == "image" and args.image_command == "decode":
            return _decode_command(args)
        if args.command == "benchmark":
            return _benchmark_command(args)
        if args.command == "serve":
            if not 1 <= args.port <= 65_535:
                raise UnoQError("Server port must be between 1 and 65535.")
            server = ThreadingHTTPServer((args.host, args.port), RequestHandler)
            print(f"LightWeave UNO Q listening on http://{args.host}:{args.port}")
            server.serve_forever()
            return 0
    except (OSError, UnoQError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        return 2
    raise AssertionError("Unhandled command.")


if __name__ == "__main__":
    raise SystemExit(main())
