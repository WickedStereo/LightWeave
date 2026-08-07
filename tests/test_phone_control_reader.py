from __future__ import annotations

import sys
from pathlib import Path

PHONE_MODULE = (
    Path(__file__).resolve().parents[1]
    / "uno_q"
    / "optical_receiver_app"
    / "python"
)
sys.path.insert(0, str(PHONE_MODULE))

from phone_usb import (  # noqa: E402
    PhoneControlReader,
    RouterMonitorTransport,
    build_control_frame,
)


class FakeBridge:
    def call(self, method: str, *params, timeout: int = 10):
        del params, timeout
        if method == "mon/connected":
            return True
        if method == "mon/read":
            return b""
        raise AssertionError(method)


def test_reader_handles_fragmentation_and_resynchronizes(tmp_path: Path) -> None:
    del tmp_path
    reader = PhoneControlReader(RouterMonitorTransport(FakeBridge()))
    frame = build_control_frame("listen")
    reader._accept(b"noise" + frame[:3])
    assert reader.commands.empty()
    reader._accept(frame[3:])
    assert reader.commands.get_nowait() == "listen"
