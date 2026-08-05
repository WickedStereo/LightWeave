"""Optional process-level guard that permits loopback but rejects network access."""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Any

_INSTALLED = False


def _loopback(host: object) -> bool:
    if isinstance(host, bytes):
        host = host.decode("ascii", errors="ignore")
    if not isinstance(host, str):
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def install_offline_guard() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    original_connect = socket.socket.connect
    original_getaddrinfo = socket.getaddrinfo

    def guarded_connect(instance: socket.socket, address: Any) -> Any:
        host = address[0] if isinstance(address, tuple) and address else None
        if not _loopback(host):
            raise OSError("LightWeave offline mode blocked non-loopback networking.")
        return original_connect(instance, address)

    def guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if not _loopback(host):
            raise OSError("LightWeave offline mode blocked DNS/network access.")
        return original_getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = guarded_connect
    socket.getaddrinfo = guarded_getaddrinfo
    _INSTALLED = True


def enforce_from_environment() -> None:
    if os.environ.get("LIGHTWEAVE_ENFORCE_OFFLINE", "").lower() in {
        "1",
        "true",
        "yes",
    }:
        install_offline_guard()
