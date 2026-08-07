"""Arduino App Lab entrypoint for optical image reception and reconstruction."""

from __future__ import annotations

import base64
import queue
import threading
import time
import uuid

from arduino.app_bricks.web_ui import WebUI
from arduino.app_utils import App, Bridge
from lightweave_optical_receiver import (
    PRESET_BUDGETS,
    ReceiveRequest,
    ReceiverError,
    ReceiverStore,
    app_root,
    build_request,
    collect_received_bytes,
)
from lightweave_uno import decode_payload

ui = WebUI()
store = ReceiverStore(app_root())
arm_queue: queue.Queue[ReceiveRequest] = queue.Queue()
payload_ready_event = threading.Event()
pending_request: ReceiveRequest | None = None


def send_status(request: ReceiveRequest | None, status: str, client=None) -> None:
    value = {
        "status": status,
        "media_type": "image",
        "presets": PRESET_BUDGETS,
        "bit_duration_ms": 25,
    }
    if request is not None:
        value.update(
            request_id=request.request_id,
            preset_code=request.preset_code,
            expected_bytes=request.expected_bytes,
        )
    ui.send_message("receiver_status", value, client)


def send_error(message: str, client=None) -> None:
    ui.send_message("receiver_error", {"error": message}, client)


def payload_ready_notification() -> None:
    payload_ready_event.set()


def arm_from_ui(client, data) -> None:
    try:
        request = build_request(
            str(uuid.uuid4()),
            (data or {}).get("preset_code"),
            (data or {}).get("expected_bytes"),
            source="web-ui",
        )
        arm_queue.put(request)
        ui.send_message("receiver_status", {"status": "arming"}, client)
    except ReceiverError as exc:
        send_error(str(exc), client)


def get_initial_state(client, _data) -> None:
    send_status(pending_request, "armed" if pending_request else "idle", client)


def next_request() -> ReceiveRequest | None:
    try:
        return arm_queue.get_nowait()
    except queue.Empty:
        return store.claim_next()


def process_completed_request(request: ReceiveRequest) -> None:
    payload = collect_received_bytes(Bridge, request.expected_bytes)
    stop_bit_valid = bool(Bridge.call("get_stop_bit_valid"))
    if not stop_bit_valid:
        raise ReceiverError("The optical stop bit was invalid.")
    store.write_state(request, "reconstructing")
    send_status(request, "reconstructing")
    png, metrics = decode_payload(payload, request.preset_code)
    result = store.write_result(
        request,
        payload,
        png,
        stop_bit_valid=stop_bit_valid,
        metrics=metrics,
    )
    ui.send_message(
        "receiver_result",
        {
            **result,
            "png_base64": base64.b64encode(png).decode("ascii"),
        },
    )


def loop() -> None:
    global pending_request
    try:
        if pending_request is None:
            request = next_request()
            if request is None:
                time.sleep(0.1)
                return
            payload_ready_event.clear()
            pending_request = request
            if not Bridge.call("start_receive", request.expected_bytes):
                raise ReceiverError("STM32 refused to arm the receiver.")
            store.write_state(request, "armed")
            send_status(request, "armed")
            return

        if not payload_ready_event.is_set():
            time.sleep(0.05)
            return

        request = pending_request
        process_completed_request(request)
        pending_request = None
        payload_ready_event.clear()
        send_status(None, "idle")
    except Exception as exc:
        message = str(exc)
        if pending_request is not None:
            store.write_error(pending_request.request_id, message)
        send_error(message)
        pending_request = None
        payload_ready_event.clear()
        store.write_state(None, "idle")
        send_status(None, "idle")
        time.sleep(0.5)


Bridge.provide("payload_ready", payload_ready_notification)
ui.on_message("arm_receiver", arm_from_ui)
ui.on_message("get_initial_state", get_initial_state)
store.write_state(None, "idle")
App.run(user_loop=loop)
