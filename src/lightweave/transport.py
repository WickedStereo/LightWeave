"""Adapter contracts for message-bounded raw byte transport."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class SendReceipt:
    """Evidence returned by a raw-byte sink after one complete message."""

    bytes_sent: int
    adapter: str
    evidence: Mapping[str, object] | None = None


@runtime_checkable
class RawByteSink(Protocol):
    """Destination for one complete, ordered raw payload."""

    def send(self, payload: bytes) -> SendReceipt: ...


@runtime_checkable
class RawByteSource(Protocol):
    """Source of one complete, ordered raw payload."""

    def receive(self) -> bytes: ...


class MemoryRawPipe:
    """Small loopback adapter used by local verification and tests."""

    def __init__(self) -> None:
        self._payload: bytes | None = None

    def send(self, payload: bytes) -> SendReceipt:
        self._payload = bytes(payload)
        return SendReceipt(len(self._payload), "memory-loopback")

    def receive(self) -> bytes:
        if self._payload is None:
            raise RuntimeError("No raw payload is available in the loopback pipe.")
        return self._payload
