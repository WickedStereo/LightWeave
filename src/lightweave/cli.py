"""LightWeave command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .audio import decode_audio, encode_audio, roundtrip_audio
from .envelope import envelope_summary, read_envelope
from .errors import LightWeaveError
from .image import encode_image, write_bytes_atomic
from .metrics import transfer_estimates
from .raw import (
    RAW_IMAGE_MAX_BYTES,
    decode_raw_audio,
    decode_raw_image,
    encode_raw_audio,
    encode_raw_image,
)
from .service import decode_image_bytes, roundtrip_image


def _print_json(value: dict[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, allow_nan=False))


def _read_artifact(path: str) -> bytes:
    if path == "-":
        return sys.stdin.buffer.read()
    return Path(path).read_bytes()


def _write_artifact(value: bytes, path: str) -> None:
    if path == "-":
        sys.stdout.buffer.write(value)
        sys.stdout.buffer.flush()
    else:
        write_bytes_atomic(value, Path(path))


def command_inspect(args: argparse.Namespace) -> None:
    value = _read_artifact(args.payload)
    from io import BytesIO

    envelope = read_envelope(BytesIO(value))
    summary = envelope_summary(envelope)
    summary.update(transfer_estimates(len(value)))
    _print_json(summary)


def command_image_encode(args: argparse.Namespace) -> None:
    encoded = encode_image(
        Path(args.input),
        allow_oversize=args.allow_oversize,
        max_envelope_bytes=args.max_bytes,
    )
    _write_artifact(encoded.envelope_bytes, args.output)
    if args.output != "-":
        summary = envelope_summary(encoded.envelope)
        summary.update(transfer_estimates(len(encoded.envelope_bytes)))
        summary["encode_seconds"] = encoded.encode_seconds
        summary["output"] = str(Path(args.output).resolve())
        _print_json(summary)


def command_image_decode(args: argparse.Namespace) -> None:
    if args.require_npu and args.backend != "qnn":
        raise ValueError("--require-npu cannot be combined with --backend cpu.")
    value = _read_artifact(args.payload)
    result = decode_image_bytes(
        value,
        backend=args.backend,
        output_path=Path(args.output),
        arm64_python=Path(args.arm64_python) if args.arm64_python else None,
        decoder_model=Path(args.decoder_model) if args.decoder_model else None,
    )
    _print_json(
        {
            "backend": result.backend,
            "output": str(Path(args.output).resolve()),
            "entropy_decode_seconds": result.entropy_decode_seconds,
            "reconstruction_seconds": result.reconstruction_seconds,
            "npu_evidence": result.evidence,
        }
    )


def command_image_roundtrip(args: argparse.Namespace) -> None:
    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    result = roundtrip_image(
        Path(args.input),
        backend=args.backend,
        payload_path=work_dir / "payload.lwv",
        output_path=work_dir / "reconstructed.png",
        allow_oversize=args.allow_oversize,
    )
    _print_json(result)


def command_audio_encode(args: argparse.Namespace) -> None:
    encoded = encode_audio(Path(args.input))
    _write_artifact(encoded.envelope_bytes, args.output)
    if args.output != "-":
        summary = envelope_summary(encoded.envelope)
        summary.update(transfer_estimates(len(encoded.envelope_bytes)))
        summary["encode_seconds"] = encoded.encode_seconds
        summary["output"] = str(Path(args.output).resolve())
        _print_json(summary)


def command_audio_decode(args: argparse.Namespace) -> None:
    value = _read_artifact(args.payload)
    result = decode_audio(
        value, backend=args.backend, output_path=Path(args.output)
    )
    _print_json(
        {
            "backend": result.backend,
            "output": str(Path(args.output).resolve()),
            "restored_samples": int(result.waveform.shape[-1]),
            "codebook_decode_seconds": result.codebook_seconds,
            "cpu_prefix_seconds": result.cpu_prefix_seconds,
            "reconstruction_seconds": result.reconstruction_seconds,
            "execution_evidence": result.evidence,
        }
    )


def command_audio_roundtrip(args: argparse.Namespace) -> None:
    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    result = roundtrip_audio(
        Path(args.input),
        backend=args.backend,
        payload_path=work_dir / "payload.lwv",
        output_path=work_dir / "reconstructed.wav",
    )
    _print_json(result)


def command_raw_image_encode(args: argparse.Namespace) -> None:
    encoded = encode_raw_image(Path(args.input))
    _write_artifact(encoded.payload, args.output)
    if args.output != "-":
        _print_json(
            {
                "preset_code": encoded.preset_code,
                "raw_bytes": len(encoded.payload),
                "maximum_bytes": RAW_IMAGE_MAX_BYTES,
                "within_budget": len(encoded.payload) <= RAW_IMAGE_MAX_BYTES,
                "effective_detail": encoded.effective_detail,
                "fallback": encoded.fallback,
                "bits_per_pixel": len(encoded.payload) * 8 / (64 * 64),
                "encode_seconds": encoded.encode_seconds,
                **transfer_estimates(len(encoded.payload)),
                "output": str(Path(args.output).resolve()),
            }
        )


def command_raw_image_decode(args: argparse.Namespace) -> None:
    if args.require_npu and args.backend != "qnn":
        raise ValueError("--require-npu cannot be combined with --backend cpu.")
    decoded = decode_raw_image(
        _read_artifact(args.payload),
        preset_code=args.preset,
        backend=args.backend,
        output_path=Path(args.output),
        arm64_python=Path(args.arm64_python) if args.arm64_python else None,
        decoder_model=Path(args.decoder_model) if args.decoder_model else None,
    )
    _print_json(
        {
            "preset_code": args.preset,
            "backend": decoded.backend,
            "output": str(Path(args.output).resolve()),
            "output_size": list(decoded.image.size),
            "entropy_decode_seconds": decoded.entropy_decode_seconds,
            "reconstruction_seconds": decoded.reconstruction_seconds,
            "npu_evidence": decoded.evidence,
        }
    )


def command_raw_audio_encode(args: argparse.Namespace) -> None:
    encoded = encode_raw_audio(Path(args.input))
    _write_artifact(encoded.payload, args.output)
    if args.output != "-":
        duration = encoded.original_samples / 24_000
        _print_json(
            {
                "preset_code": encoded.preset_code,
                "raw_bytes": len(encoded.payload),
                "chunk_count": encoded.chunk_count,
                "bytes_per_chunk": 188,
                "original_samples": encoded.original_samples,
                "code_payload_bps": len(encoded.payload) * 8 / duration,
                "encode_seconds": encoded.encode_seconds,
                **transfer_estimates(len(encoded.payload)),
                "output": str(Path(args.output).resolve()),
            }
        )


def command_raw_audio_decode(args: argparse.Namespace) -> None:
    decoded = decode_raw_audio(
        _read_artifact(args.payload),
        preset_code=args.preset,
        backend=args.backend,
        output_path=Path(args.output),
    )
    _print_json(
        {
            "preset_code": args.preset,
            "backend": decoded.backend,
            "output": str(Path(args.output).resolve()),
            "restored_samples": int(decoded.waveform.shape[-1]),
            "codebook_decode_seconds": decoded.codebook_seconds,
            "cpu_prefix_seconds": decoded.cpu_prefix_seconds,
            "reconstruction_seconds": decoded.reconstruction_seconds,
            "execution_evidence": decoded.evidence,
        }
    )


def command_dashboard(args: argparse.Namespace) -> None:
    from .dashboard import run_dashboard

    run_dashboard(port=args.port)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="lightweave", description=__doc__)
    subcommands = root.add_subparsers(dest="command", required=True)

    inspect_parser = subcommands.add_parser("inspect", help="Inspect a .lwv artifact")
    inspect_parser.add_argument("payload", help="Artifact path, or - for stdin")
    inspect_parser.set_defaults(handler=command_inspect)

    image_parser = subcommands.add_parser("image", help="Image media operations")
    image_commands = image_parser.add_subparsers(dest="image_command", required=True)

    encode = image_commands.add_parser("encode", help="Encode an image into .lwv")
    encode.add_argument("input")
    encode.add_argument("--output", "-o", required=True)
    encode.add_argument("--max-bytes", type=int, default=2048)
    encode.add_argument("--allow-oversize", action="store_true")
    encode.set_defaults(handler=command_image_encode)

    decode = image_commands.add_parser("decode", help="Decode an image .lwv")
    decode.add_argument("payload", help="Artifact path, or - for stdin")
    decode.add_argument("--output", "-o", required=True)
    decode.add_argument("--backend", choices=("qnn", "cpu"), default="qnn")
    decode.add_argument("--require-npu", action="store_true")
    decode.add_argument("--arm64-python")
    decode.add_argument("--decoder-model")
    decode.set_defaults(handler=command_image_decode)

    roundtrip = image_commands.add_parser(
        "roundtrip", help="Encode and decode an image in one local workflow"
    )
    roundtrip.add_argument("input")
    roundtrip.add_argument("--work-dir", required=True)
    roundtrip.add_argument("--backend", choices=("qnn", "cpu"), default="qnn")
    roundtrip.add_argument("--allow-oversize", action="store_true")
    roundtrip.set_defaults(handler=command_image_roundtrip)

    audio_parser = subcommands.add_parser("audio", help="Audio media operations")
    audio_commands = audio_parser.add_subparsers(
        dest="audio_command", required=True
    )

    audio_encode = audio_commands.add_parser(
        "encode", help="Encode a PCM WAV into .lwv"
    )
    audio_encode.add_argument("input")
    audio_encode.add_argument("--output", "-o", required=True)
    audio_encode.set_defaults(handler=command_audio_encode)

    audio_decode = audio_commands.add_parser("decode", help="Decode an audio .lwv")
    audio_decode.add_argument("payload", help="Artifact path, or - for stdin")
    audio_decode.add_argument("--output", "-o", required=True)
    audio_decode.add_argument(
        "--backend", choices=("hybrid-qnn", "cpu"), default="hybrid-qnn"
    )
    audio_decode.set_defaults(handler=command_audio_decode)

    audio_roundtrip = audio_commands.add_parser(
        "roundtrip", help="Encode and decode audio in one local workflow"
    )
    audio_roundtrip.add_argument("input")
    audio_roundtrip.add_argument("--work-dir", required=True)
    audio_roundtrip.add_argument(
        "--backend", choices=("hybrid-qnn", "cpu"), default="hybrid-qnn"
    )
    audio_roundtrip.set_defaults(handler=command_audio_roundtrip)

    raw_parser = subcommands.add_parser(
        "raw", help="Header-free optical payload operations"
    )
    raw_media = raw_parser.add_subparsers(dest="raw_media", required=True)

    raw_image = raw_media.add_parser("image", help="Raw I64-Q1 image operations")
    raw_image_commands = raw_image.add_subparsers(
        dest="raw_image_command", required=True
    )
    raw_image_encode = raw_image_commands.add_parser(
        "encode", help="Encode an image into raw entropy bytes"
    )
    raw_image_encode.add_argument("input")
    raw_image_encode.add_argument("--output", "-o", required=True)
    raw_image_encode.set_defaults(handler=command_raw_image_encode)
    raw_image_decode = raw_image_commands.add_parser(
        "decode", help="Decode raw I64-Q1 entropy bytes"
    )
    raw_image_decode.add_argument("payload", help="Payload path, or - for stdin")
    raw_image_decode.add_argument("--preset", required=True)
    raw_image_decode.add_argument("--output", "-o", required=True)
    raw_image_decode.add_argument("--backend", choices=("qnn", "cpu"), default="qnn")
    raw_image_decode.add_argument("--require-npu", action="store_true")
    raw_image_decode.add_argument("--arm64-python")
    raw_image_decode.add_argument("--decoder-model")
    raw_image_decode.set_defaults(handler=command_raw_image_decode)

    raw_audio = raw_media.add_parser("audio", help="Raw A1-E15 audio operations")
    raw_audio_commands = raw_audio.add_subparsers(
        dest="raw_audio_command", required=True
    )
    raw_audio_encode = raw_audio_commands.add_parser(
        "encode", help="Encode a PCM WAV into raw EnCodec bytes"
    )
    raw_audio_encode.add_argument("input")
    raw_audio_encode.add_argument("--output", "-o", required=True)
    raw_audio_encode.set_defaults(handler=command_raw_audio_encode)
    raw_audio_decode = raw_audio_commands.add_parser(
        "decode", help="Decode raw EnCodec bytes"
    )
    raw_audio_decode.add_argument("payload", help="Payload path, or - for stdin")
    raw_audio_decode.add_argument("--preset", required=True)
    raw_audio_decode.add_argument("--output", "-o", required=True)
    raw_audio_decode.add_argument(
        "--backend", choices=("hybrid-qnn", "cpu"), default="hybrid-qnn"
    )
    raw_audio_decode.set_defaults(handler=command_raw_audio_decode)

    dashboard = subcommands.add_parser("dashboard", help="Run the offline local UI")
    dashboard.add_argument("--port", type=int, default=8765)
    dashboard.set_defaults(handler=command_dashboard)
    return root


def main() -> None:
    if os.environ.get("LIGHTWEAVE_ENFORCE_OFFLINE"):
        from .offline import enforce_from_environment

        enforce_from_environment()
    args = parser().parse_args()
    try:
        args.handler(args)
    except (LightWeaveError, FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
