"""Arduino App Lab entrypoint for one-shot LWF1 media reception."""

from __future__ import annotations

import base64
import queue
import threading
import time
import uuid
from contextlib import suppress

from arduino.app_bricks.web_ui import WebUI
from arduino.app_utils import App, Bridge
from lightweave_optical_receiver import (
    ReceiveRequest,
    ReceiverError,
    ReceiverStore,
    RejectedFrameError,
    app_root,
    build_request,
    collect_received_frame,
)
from lightweave_uno import decode_audio_payload, decode_payload

ui = WebUI()
store = ReceiverStore(app_root())
listen_queue: queue.Queue[ReceiveRequest] = queue.Queue()
frame_finished_event = threading.Event()
cancel_event = threading.Event()
pending_request: ReceiveRequest | None = None


def send_status(request: ReceiveRequest | None, status: str, client=None) -> None:
    value = {
        "status": status,
        "wire_format": "LWF1",
        "bit_duration_ms": 25,
        "automatic_profile": True,
    }
    if request is not None:
        value.update(request_id=request.request_id, source=request.source)
    ui.send_message("receiver_status", value, client)


def send_error(message: str, client=None) -> None:
    ui.send_message("receiver_error", {"error": message}, client)


def frame_finished_notification() -> None:
    frame_finished_event.set()


def listen_from_ui(client, _data) -> None:
    if pending_request is not None or not listen_queue.empty():
        send_error("The receiver is already listening for a transfer.", client)
        return
    request = build_request(str(uuid.uuid4()), source="web-ui")
    listen_queue.put(request)
    ui.send_message("receiver_status", {"status": "arming"}, client)


def cancel_from_ui(client, _data) -> None:
    if pending_request is None and listen_queue.empty():
        send_status(None, "idle", client)
        return
    cancel_event.set()
    ui.send_message("receiver_status", {"status": "cancelling"}, client)


def get_initial_state(client, _data) -> None:
    send_status(pending_request, "listening" if pending_request else "idle", client)


def next_request() -> ReceiveRequest | None:
    try:
        return listen_queue.get_nowait()
    except queue.Empty:
        return store.claim_next()


def process_completed_request(request: ReceiveRequest) -> None:
    frame = collect_received_frame(Bridge)
    store.write_state(request, "reconstructing")
    send_status(request, "reconstructing")
    if frame.header.profile.media_type == "image":
        media, metrics = decode_payload(frame.payload, frame.header.preset_code)
        extension = "png"
        base64_field = "png_base64"
        text_content = None
    elif frame.header.profile.media_type == "audio":
        media, metrics = decode_audio_payload(frame.payload, frame.header.preset_code)
        extension = "wav"
        base64_field = "wav_base64"
        text_content = None
    else:
        text_content = frame.payload.decode("ascii")
        media = frame.payload
        metrics = {
            "backend": "printable-ascii",
            "decoder": "strict ASCII bytes",
            "accelerator_required": False,
            "characters": len(text_content),
        }
        extension = "txt"
        base64_field = None
    result = store.write_result(
        request,
        frame,
        media,
        output_extension=extension,
        metrics=metrics,
    )
    response = dict(result)
    if base64_field is not None:
        response[base64_field] = base64.b64encode(media).decode("ascii")
    else:
        response["text_content"] = text_content
    ui.send_message("receiver_result", response)


def clear_pending() -> None:
    global pending_request
    pending_request = None
    frame_finished_event.clear()
    cancel_event.clear()


def loop() -> None:
    global pending_request
    try:
        if pending_request is None:
            if cancel_event.is_set():
                with suppress(queue.Empty):
                    listen_queue.get_nowait()
                cancel_event.clear()
                store.write_state(None, "idle")
                send_status(None, "idle")
                return
            request = next_request()
            if request is None:
                time.sleep(0.1)
                return
            frame_finished_event.clear()
            cancel_event.clear()
            pending_request = request
            if not Bridge.call("start_listen"):
                raise ReceiverError("STM32 refused to start one-shot listening.")
            store.write_state(request, "listening")
            send_status(request, "listening")
            return

        if cancel_event.is_set():
            Bridge.call("cancel_receive")
            request = pending_request
            store.write_error(request.request_id, "Optical listen cancelled.")
            clear_pending()
            store.write_state(None, "idle")
            send_status(None, "idle")
            return

        if not frame_finished_event.is_set():
            time.sleep(0.05)
            return

        request = pending_request
        process_completed_request(request)
        Bridge.call("reset_receiver")
        clear_pending()
        store.write_state(None, "idle")
        send_status(None, "idle")
    except Exception as exc:
        message = str(exc)
        if pending_request is not None:
            if isinstance(exc, RejectedFrameError):
                store.write_error(
                    pending_request.request_id,
                    message,
                    evidence=exc.evidence,
                    payload=exc.payload,
                )
            else:
                store.write_error(pending_request.request_id, message)
        with suppress(Exception):
            Bridge.call("reset_receiver")
        send_error(message)
        clear_pending()
        store.write_state(None, "idle")
        send_status(None, "idle")
        time.sleep(0.5)


Bridge.provide("frame_finished", frame_finished_notification)
ui.on_message("listen_receiver", listen_from_ui)
ui.on_message("cancel_receiver", cancel_from_ui)
ui.on_message("get_initial_state", get_initial_state)
store.write_state(None, "idle")
App.run(user_loop=loop)
