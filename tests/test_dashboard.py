from __future__ import annotations

from fastapi.testclient import TestClient

from lightweave.dashboard import create_app


def test_dashboard_is_local_and_offline() -> None:
    with TestClient(create_app()) as client:
        status = client.get("/api/status")
        assert status.status_code == 200
        assert status.json()["offline"] is True
        assert status.json()["bind_host"] == "127.0.0.1"


def test_dashboard_serves_only_local_assets() -> None:
    with TestClient(create_app()) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert 'href="/static/styles.css"' in page.text
        assert 'src="/static/app.js"' in page.text
        assert "https://" not in page.text
        assert client.get("/static/styles.css").status_code == 200
