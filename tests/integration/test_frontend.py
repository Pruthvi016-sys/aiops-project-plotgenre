"""Frontend server - static UI, config, proxy allow-list, telemetry."""

import httpx
import pytest
from fastapi.testclient import TestClient

from frontend.app import main as fe

pytestmark = pytest.mark.integration


@pytest.fixture
def client(monkeypatch):
    seen = {}

    def handler(request):
        seen["key"] = request.headers.get("X-API-Key")
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"ok": True})
    monkeypatch.setattr(fe, "client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(fe, "API_KEY", "secret-123")
    c = TestClient(fe.app)
    c.seen = seen
    return c


def test_index_and_static(client):
    r = client.get("/")
    assert r.status_code == 200 and "PlotGenre" in r.text
    assert client.get("/static/app.js").status_code == 200


def test_config_exposes_no_secret(client):
    body = client.get("/config.js").text
    assert "PLOTGENRE_CONFIG" in body and "secret-123" not in body


def test_proxy_adds_key_and_respects_allow_list(client):
    assert client.post("/api/gateway/api/v1/predict", json={"text": "x"}).json() == {"ok": True}
    assert client.seen["key"] == "secret-123"
    assert client.seen["url"].endswith("/api/v1/predict")
    assert client.get("/api/gateway/admin/delete").status_code == 404
    assert client.get("/api/unknown/health").status_code == 404
    assert client.get("/api/pipeline/api/v1/pipeline/runs/../../etc/log").status_code == 404


def test_backend_unreachable(monkeypatch):
    def boom(request):
        raise httpx.ConnectError("down", request=request)
    monkeypatch.setattr(fe, "client", httpx.AsyncClient(transport=httpx.MockTransport(boom)))
    r = TestClient(fe.app).get("/api/gateway/health")
    assert r.status_code == 503 and r.json()["error"]["code"] == "backend_unreachable"


def test_telemetry_metrics(client):
    assert client.post("/telemetry", json={"type": "page_load", "page": "classify",
                                           "duration_ms": 300}).status_code == 204
    assert client.post("/telemetry", json={"type": "ui_error", "page": "classify",
                                           "name": "timeout"}).status_code == 204
    assert client.post("/telemetry", json={"type": "bogus"}).status_code == 422
    text = client.get("/metrics").text
    assert 'plotgenre_frontend_page_loads_total{page="classify"}' in text
    assert "plotgenre_frontend_ui_errors_total" in text
