"""Gateway REST API with a mocked MLflow model server."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from gateway.app import main as gw
from gateway.app.clients import ModelServerClient, RegistryClient

pytestmark = pytest.mark.integration
KEY = {"X-API-Key": "test-key"}
PLOT = ("A detective hunts a serial killer through the rainy city while his own past "
        "catches up with him and the police department turns against him. In the end he "
        "must choose between justice and revenge.")


def model_server(mode="ok"):
    def handler(request: httpx.Request):
        if mode == "down":
            raise httpx.ConnectError("refused", request=request)
        if request.url.path == "/ping":
            return httpx.Response(200)
        if mode == "error":
            return httpx.Response(500, text="boom")
        n = len(json.loads(request.content)["dataframe_records"])
        genres = [{"genre": "Crime", "confidence": 0.9, "predicted": True},
                  {"genre": "Comedy", "confidence": 0.1, "predicted": False}]
        kw = [{"word": "detective", "genre": "Crime", "weight": 0.4}]
        return httpx.Response(200, json={"predictions": [
            {"genres": json.dumps(genres), "keywords": json.dumps(kw), "threshold": 0.3,
             "model_name": "linear_svm"}] * n})
    return httpx.MockTransport(handler)


def registry():
    def handler(request: httpx.Request):
        if request.url.path.endswith("/alias"):
            return httpx.Response(200, json={"model_version": {
                "version": "7", "run_id": "abc", "tags": [{"key": "best_model", "value": "linear_svm"}]}})
        return httpx.Response(200, json={"run": {"info": {"experiment_id": "1"},
                                                 "data": {"metrics": [{"key": "test_micro_f1", "value": 0.66}]}}})
    return httpx.MockTransport(handler)


@pytest.fixture
def client_factory(tmp_path):
    ref = tmp_path / "drift_reference.json"
    ref.write_text(json.dumps({"terms": {"detective": 0.2, "killer": 0.1}, "label_prior": {
        "Crime": 0.5, "Comedy": 0.5}, "threshold": 1.5, "online_window": 20,
        "online_noise_floor_js": 0.2, "data_version": "v1"}))

    def make(mode="ok"):
        c = TestClient(gw.app)
        c.__enter__()
        gw.app.state.model = ModelServerClient("http://ms", retries=1, transport=model_server(mode))
        gw.app.state.registry = RegistryClient("http://mlflow", "m", "champion", transport=registry())
        gw.app.state.drift = gw.DriftMonitor(str(ref))
        return c
    clients = []

    def factory(mode="ok"):
        clients.append(make(mode))
        return clients[-1]
    yield factory
    for c in clients:
        c.__exit__(None, None, None)


def test_health_needs_no_auth(client_factory):
    r = client_factory().get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_ready_reflects_model_server(client_factory):
    assert client_factory().get("/ready").status_code == 200
    assert client_factory("down").get("/ready").status_code == 503


def test_predict_requires_api_key(client_factory):
    r = client_factory().post("/api/v1/predict", json={"text": PLOT})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


def test_predict_success_contract(client_factory):
    r = client_factory().post("/api/v1/predict", json={"text": PLOT}, headers=KEY)
    assert r.status_code == 200
    body = r.json()
    assert body["predicted_genres"] == ["Crime"]
    assert body["keywords"][0]["word"] == "detective"
    assert body["model"]["version"] == "7" and body["model"]["algorithm"] == "linear_svm"
    assert "X-Request-ID" in r.headers and body["warnings"] == []


@pytest.mark.parametrize("payload,code", [({"text": "too short"}, "text_too_short"),
                                          ({"text": "   "}, "empty_text"),
                                          ({"text": PLOT, "top_k": 99}, "invalid_input"),
                                          ({}, "invalid_input")])
def test_predict_validation(client_factory, payload, code):
    r = client_factory().post("/api/v1/predict", json=payload, headers=KEY)
    assert r.status_code == 422 and r.json()["error"]["code"] == code


def test_short_text_warning(client_factory):
    r = client_factory().post("/api/v1/predict", json={"text": "a man fights a dragon at night"},
                              headers=KEY)
    assert r.status_code == 200 and r.json()["warnings"]


def test_model_server_down_gives_503(client_factory):
    r = client_factory("down").post("/api/v1/predict", json={"text": PLOT}, headers=KEY)
    assert r.status_code == 503 and r.json()["error"]["code"] == "model_unavailable"


def test_model_server_error_gives_502(client_factory):
    r = client_factory("error").post("/api/v1/predict", json={"text": PLOT}, headers=KEY)
    assert r.status_code == 502


def test_batch(client_factory):
    c = client_factory()
    r = c.post("/api/v1/predict/batch", json={"texts": [PLOT, PLOT]}, headers=KEY)
    assert r.status_code == 200 and r.json()["count"] == 2
    r = c.post("/api/v1/predict/batch", json={"texts": [PLOT] * 51}, headers=KEY)
    assert r.status_code == 422 and r.json()["error"]["code"] == "batch_too_large"


def test_model_info_and_genres(client_factory):
    c = client_factory()
    info = c.get("/api/v1/model", headers=KEY).json()
    assert info["version"] == "7" and info["metrics"]["test_micro_f1"] == 0.66
    assert "/runs/abc" in info["mlflow_run_url"]
    assert c.get("/api/v1/genres").json() == ["Comedy", "Crime"]


def test_metrics_and_live_drift(client_factory):
    c = client_factory()
    for _ in range(12):
        c.post("/api/v1/predict", json={"text": PLOT}, headers=KEY)
    drift = c.get("/api/v1/monitoring/drift", headers=KEY).json()
    assert drift["reference_loaded"] and drift["window_size"] == 12
    assert drift["drift_score"] is not None
    text = c.get("/metrics").text
    for name in ("plotgenre_gateway_requests_total", "plotgenre_upstream_latency_seconds",
                 "plotgenre_predicted_genre_total", "plotgenre_live_drift_score"):
        assert name in text
