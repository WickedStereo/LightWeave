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

from phone_usb import PhoneControlReader, build_control_frame  # noqa: E402


def test_reader_handles_fragmentation_and_resynchronizes(tmp_path: Path) -> None:
    reader = PhoneControlReader(tmp_path / "ttyGS0")
    frame = build_control_frame("listen")
    reader._accept(b"noise" + frame[:3])
    assert reader.commands.empty()
    reader._accept(frame[3:])
    assert reader.commands.get_nowait() == "listen"
