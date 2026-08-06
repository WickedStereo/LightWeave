from __future__ import annotations

from fastapi.testclient import TestClient

from lightweave.dashboard import create_app
from lightweave.transport import SendReceipt


class FakeUnoQSink:
    def __init__(self, *, media_type: str, preset_code: str) -> None:
        self.media_type = media_type
        self.preset_code = preset_code

    def status(self) -> dict[str, object]:
        return {
            "connected": True,
            "ready": True,
            "device": "Arduino UNO Q",
            "transport": "usb-adb-inbox",
            "app_status": "running",
            "busy": False,
        }

    def send(self, payload: bytes) -> SendReceipt:
        return SendReceipt(
            len(payload),
            "uno-q-app-lab-adb",
            {
                "accepted": True,
                "request_id": "00000000-0000-4000-8000-000000000000",
                "media_type": self.media_type,
                "preset_code": self.preset_code,
                "payload_bytes": len(payload),
                "buffered_bytes": len(payload),
                "optical_bits": len(payload) * 8 + 2,
                "estimated_transmission_seconds": (len(payload) * 8 + 2) * 0.025,
            },
        )


def test_dashboard_is_local_and_offline() -> None:
    with TestClient(create_app()) as client:
        status = client.get("/api/status")
        assert status.status_code == 200
        assert status.json()["offline"] is True
        assert status.json()["bind_host"] == "127.0.0.1"


def test_dashboard_serves_only_local_assets() -> None:
    with TestClient(create_app()) as client:
        redirect = client.get("/", follow_redirects=False)
        assert redirect.status_code == 307
        assert redirect.headers["location"] == "/transmit"
        page = client.get("/transmit")
        assert page.status_code == 200
        assert 'href="/static/styles.css"' in page.text
        assert 'src="/static/transmit.js"' in page.text
        assert "I128-Q1-B768" in page.text
        assert "send to Arduino" in page.text
        assert "https://" not in page.text
        transmitter_script = client.get("/static/transmit.js")
        assert transmitter_script.status_code == 200
        assert "confirm send" in transmitter_script.text
        assert "window.confirm" not in transmitter_script.text
        receive = client.get("/receive")
        assert receive.status_code == 200
        assert 'src="/static/receive.js"' in receive.text
        loopback = client.get("/loopback")
        assert loopback.status_code == 200
        assert 'src="/static/app.js"' in loopback.text
        assert client.get("/static/styles.css").status_code == 200


def test_dashboard_exposes_uno_q_status_and_transmit_contract() -> None:
    with TestClient(create_app(uno_q_sink_factory=FakeUnoQSink)) as client:
        status = client.get("/api/adapters/uno-q/status")
        assert status.status_code == 200
        assert status.json()["ready"] is True
        response = client.post(
            "/api/adapters/uno-q/transmit",
            data={"media_type": "image", "preset_code": "I64-Q1-B128"},
            files={"file": ("payload.bin", bytes(80))},
        )
        assert response.status_code == 200
        assert response.json()["buffered_bytes"] == 80
        assert response.json()["optical_bits"] == 642


def test_dashboard_serves_small_local_test_patterns() -> None:
    with TestClient(create_app()) as client:
        for name in ("gradient", "blocks", "rings"):
            sample = client.get(f"/api/samples/image/{name}")
            assert sample.status_code == 200
            assert sample.headers["content-type"] == "image/png"
            assert sample.content.startswith(b"\x89PNG")
        assert client.get("/api/samples/image/unknown").status_code == 404


def test_raw_receive_contract_errors_precede_model_loading() -> None:
    with TestClient(create_app()) as client:
        image = client.post(
            "/api/receive/image",
            data={"preset_code": "wrong", "backend": "cpu"},
            files={"file": ("payload.bin", b"one byte")},
        )
        assert image.status_code == 422
        assert "Unsupported raw image preset" in image.json()["detail"]

        audio = client.post(
            "/api/receive/audio",
            data={"preset_code": "A1-E15-S24000", "backend": "cpu"},
            files={"file": ("payload.bin", bytes(187))},
        )
        assert audio.status_code == 422
        assert "divisible by 188" in audio.json()["detail"]
