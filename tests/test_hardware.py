from __future__ import annotations

import sys

from lightweave.hardware import OperationMonitor, host_inventory


def test_host_inventory_is_portable_and_nonempty() -> None:
    inventory = host_inventory()
    assert inventory["system"]
    assert inventory["architecture"]
    assert inventory["process_architecture"]
    assert inventory["os_architecture"]
    assert inventory["processor"]
    assert (
        inventory["logical_processors"] is None or inventory["logical_processors"] > 0
    )


def test_operation_monitor_labels_measurement_scope_and_counters() -> None:
    monitor = OperationMonitor("fixture")
    usage = monitor.finish(
        stages=[{"processor": "CPU", "stage": "fixture work", "used": True}],
        counters={"bytes": 4},
        accelerator_note="No accelerator used.",
    )
    measurement = usage["process_measurement"]
    assert usage["operation"] == "fixture"
    assert usage["counters"] == {"bytes": 4}
    assert measurement["wall_seconds"] >= 0
    assert measurement["process_cpu_seconds"] >= 0
    assert "process-lifetime high-water mark" in measurement["scope"]
    if sys.platform == "win32":
        assert measurement["peak_process_rss_bytes"] > 0
    assert usage["accelerator_note"] == "No accelerator used."
