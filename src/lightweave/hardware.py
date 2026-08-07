"""Portable, dependency-free hardware telemetry for user-visible operations."""

from __future__ import annotations

import os
import platform
import sys
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any


def _peak_rss_bytes() -> int | None:
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            kernel32 = ctypes.windll.kernel32
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            process = kernel32.GetCurrentProcess()
            get_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
            get_memory_info.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(ProcessMemoryCounters),
                wintypes.DWORD,
            ]
            get_memory_info.restype = wintypes.BOOL
            if get_memory_info(process, ctypes.byref(counters), counters.cb):
                return int(counters.PeakWorkingSetSize)
        except (AttributeError, OSError, TypeError, ValueError):
            return None
        return None
    try:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return value if sys.platform == "darwin" else value * 1024
    except (ImportError, OSError, ValueError):
        return None


@lru_cache(maxsize=1)
def host_inventory() -> dict[str, Any]:
    processor = (
        os.environ.get("PROCESSOR_IDENTIFIER") or platform.processor() or "unknown"
    )
    process_architecture = platform.machine()
    return {
        "system": platform.system(),
        "release": platform.release(),
        "architecture": process_architecture,
        "process_architecture": process_architecture,
        "os_architecture": (
            os.environ.get("PROCESSOR_ARCHITECTURE") or process_architecture
        ),
        "processor": processor,
        "logical_processors": os.cpu_count(),
    }


@dataclass(slots=True)
class OperationMonitor:
    """Measure this Python process; accelerator evidence is supplied separately."""

    operation: str
    wall_started: float = field(default_factory=time.perf_counter)
    cpu_started: float = field(default_factory=time.process_time)
    rss_started: int | None = field(default_factory=_peak_rss_bytes)

    def finish(
        self,
        *,
        stages: list[dict[str, Any]],
        counters: dict[str, int | float | str | bool | None] | None = None,
        accelerator_note: str,
    ) -> dict[str, Any]:
        wall_seconds = max(0.0, time.perf_counter() - self.wall_started)
        process_cpu_seconds = max(0.0, time.process_time() - self.cpu_started)
        logical_processors = os.cpu_count() or 1
        one_core_percent = (
            process_cpu_seconds / wall_seconds * 100.0 if wall_seconds else 0.0
        )
        peak_rss = _peak_rss_bytes()
        return {
            "operation": self.operation,
            "host": host_inventory(),
            "process_measurement": {
                "wall_seconds": wall_seconds,
                "process_cpu_seconds": process_cpu_seconds,
                "average_cpu_percent_one_core": one_core_percent,
                "average_cpu_percent_total_capacity": (
                    one_core_percent / logical_processors
                ),
                "peak_process_rss_bytes": peak_rss,
                "peak_process_rss_mib": (
                    peak_rss / (1024 * 1024) if peak_rss is not None else None
                ),
                "peak_rss_at_start_bytes": self.rss_started,
                "scope": (
                    "current Python dashboard process only; peak RSS is a "
                    "process-lifetime high-water mark"
                ),
            },
            "stages": stages,
            "counters": counters or {},
            "accelerator_note": accelerator_note,
        }
