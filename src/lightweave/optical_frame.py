"""Shared LightWeave LWF1 optical framing contract.

The raw codec payload is never modified by this module.  LWF1 exists only on
the optical wire and carries the information a one-shot receiver needs.
"""

from __future__ import annotations

from dataclasses import dataclass

MAGIC = b"LW"
FRAME_VERSION = 1
HEADER_BYTES = 10
CRC_BYTES = 2
FRAME_OVERHEAD_BYTES = HEADER_BYTES + CRC_BYTES
BIT_DURATION_MS = 25

AUDIO_CHUNK_BYTES = 188
AUDIO_SAMPLES_PER_CHUNK = 24_000
MAX_AUDIO_BYTES = 940
MAX_AUDIO_SAMPLES = 120_000


class FrameError(ValueError):
    """An LWF1 header or payload violates the optical contract."""


@dataclass(frozen=True, slots=True)
class Profile:
    profile_id: int
    preset_code: str
    media_type: str
    maximum_bytes: int


PROFILES = (
    Profile(0x01, "I64-Q1-B128", "image", 128),
    Profile(0x02, "I128-Q1-B768", "image", 768),
    Profile(0x03, "I256-Q1-B2048", "image", 2_048),
    Profile(0x10, "A1-E15-S<n>", "audio", MAX_AUDIO_BYTES),
    Profile(0x20, "T1-ASCII-B100", "text", 100),
)
PROFILE_BY_ID = {profile.profile_id: profile for profile in PROFILES}
PROFILE_BY_PRESET = {
    profile.preset_code: profile
    for profile in PROFILES
    if profile.media_type != "audio"
}


@dataclass(frozen=True, slots=True)
class Header:
    profile: Profile
    payload_bytes: int
    media_parameter: int

    @property
    def preset_code(self) -> str:
        if self.profile.media_type == "audio":
            return f"A1-E15-S{self.media_parameter}"
        return self.profile.preset_code


def crc16_ccitt_false(data: bytes) -> int:
    """Return CRC-16/CCITT-FALSE (poly 0x1021, init 0xffff)."""

    crc = 0xFFFF
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = (
                ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
            )
    return crc


def profile_for_preset(preset_code: str) -> tuple[Profile, int]:
    profile = PROFILE_BY_PRESET.get(preset_code)
    if profile is not None:
        return profile, 0
    prefix = "A1-E15-S"
    if not preset_code.startswith(prefix):
        raise FrameError("Unsupported LightWeave preset code.")
    sample_text = preset_code[len(prefix) :]
    if not sample_text.isdigit() or sample_text.startswith("0"):
        raise FrameError("Malformed audio preset; expected A1-E15-S<n>.")
    return PROFILE_BY_ID[0x10], int(sample_text)


def validate_contract(
    profile: Profile,
    payload_bytes: int,
    media_parameter: int,
    payload: bytes | None = None,
) -> None:
    if payload_bytes < 1 or payload_bytes > profile.maximum_bytes:
        raise FrameError(
            f"Payload length must be between 1 and {profile.maximum_bytes} bytes "
            f"for {profile.preset_code}."
        )
    if payload is not None and len(payload) != payload_bytes:
        raise FrameError("Declared payload length does not match the payload.")
    if profile.media_type in {"image", "text"}:
        if media_parameter != 0:
            raise FrameError(
                f"{profile.media_type.capitalize()} media parameter must be zero."
            )
        if (
            profile.media_type == "text"
            and payload is not None
            and any(value < 32 or value > 126 for value in payload)
        ):
            raise FrameError("Text payload contains non-printable ASCII bytes.")
        return
    if payload_bytes % AUDIO_CHUNK_BYTES:
        raise FrameError("Audio payload length must be divisible by 188 bytes.")
    chunks = payload_bytes // AUDIO_CHUNK_BYTES
    minimum = (chunks - 1) * AUDIO_SAMPLES_PER_CHUNK + 1
    maximum = chunks * AUDIO_SAMPLES_PER_CHUNK
    if not minimum <= media_parameter <= maximum:
        raise FrameError("Audio sample count is impossible for the payload length.")
    if media_parameter > MAX_AUDIO_SAMPLES:
        raise FrameError("Audio sample count exceeds the five-second limit.")
    if payload is not None:
        for offset in range(0, payload_bytes, AUDIO_CHUNK_BYTES):
            if payload[offset + AUDIO_CHUNK_BYTES - 1] & 0xF0:
                raise FrameError("Audio chunk has non-zero padding bits.")


def build_header(preset_code: str, payload_bytes: int) -> bytes:
    profile, media_parameter = profile_for_preset(preset_code)
    validate_contract(profile, payload_bytes, media_parameter)
    return b"".join(
        (
            MAGIC,
            bytes((FRAME_VERSION, profile.profile_id)),
            payload_bytes.to_bytes(2, "little"),
            media_parameter.to_bytes(4, "little"),
        )
    )


def parse_header(data: bytes) -> Header:
    if len(data) != HEADER_BYTES:
        raise FrameError("LWF1 header must be exactly 10 bytes.")
    if data[:2] != MAGIC:
        raise FrameError("Invalid LWF1 magic.")
    if data[2] != FRAME_VERSION:
        raise FrameError("Unsupported LWF1 frame version.")
    profile = PROFILE_BY_ID.get(data[3])
    if profile is None:
        raise FrameError("Unsupported LWF1 profile ID.")
    payload_bytes = int.from_bytes(data[4:6], "little")
    media_parameter = int.from_bytes(data[6:10], "little")
    validate_contract(profile, payload_bytes, media_parameter)
    return Header(profile, payload_bytes, media_parameter)


def build_frame(payload: bytes, preset_code: str) -> bytes:
    header = build_header(preset_code, len(payload))
    parsed = parse_header(header)
    validate_contract(parsed.profile, len(payload), parsed.media_parameter, payload)
    crc = crc16_ccitt_false(header + payload)
    return header + payload + crc.to_bytes(2, "little")


def parse_frame(frame: bytes) -> tuple[Header, bytes, int]:
    if len(frame) < FRAME_OVERHEAD_BYTES + 1:
        raise FrameError("LWF1 frame is truncated.")
    header_bytes = frame[:HEADER_BYTES]
    header = parse_header(header_bytes)
    expected = header.payload_bytes + FRAME_OVERHEAD_BYTES
    if len(frame) != expected:
        raise FrameError("LWF1 frame length does not match its header.")
    payload = frame[HEADER_BYTES : HEADER_BYTES + header.payload_bytes]
    validate_contract(header.profile, len(payload), header.media_parameter, payload)
    received_crc = int.from_bytes(frame[-CRC_BYTES:], "little")
    computed_crc = crc16_ccitt_false(header_bytes + payload)
    if received_crc != computed_crc:
        raise FrameError("LWF1 CRC mismatch.")
    return header, payload, received_crc


def optical_bits(payload_bytes: int, mode: str = "lwf1") -> int:
    if payload_bytes < 1:
        raise FrameError("Payload is empty.")
    if mode == "lwf1":
        return (payload_bytes + FRAME_OVERHEAD_BYTES) * 8 + 2
    if mode == "raw-v0":
        return payload_bytes * 8 + 2
    raise FrameError("Wire mode must be lwf1 or raw-v0.")


def transmission_seconds(payload_bytes: int, mode: str = "lwf1") -> float:
    return optical_bits(payload_bytes, mode) * BIT_DURATION_MS / 1_000
