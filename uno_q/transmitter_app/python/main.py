"""Arduino App Lab entrypoint for the LightWeave transmitter."""

from __future__ import annotations

import time

from arduino.app_utils import App, Bridge
from lightweave_transmitter import InboxWorker, app_root

worker = InboxWorker(app_root(), Bridge)


def loop() -> None:
    if not worker.process_once():
        time.sleep(0.1)


App.run(user_loop=loop)
