"""Tests against the running stack (docker compose up).

Enable with:
    E2E_FRONTEND_URL=http://localhost:8080 E2E_GATEWAY_URL=http://localhost:8000 \
    E2E_API_KEY=$(grep ^API_KEY= .env | cut -d= -f2) pytest -m e2e
"""

import json
import os
import statistics
import time
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.e2e
FE = os.environ.get("E2E_FRONTEND_URL")
GW = os.environ.get("E2E_GATEWAY_URL")
KEY = os.environ.get("E2E_API_KEY", "")
ROOT = Path(__file__).resolve().parents[2]
HEIST = ("Four old friends plan one last robbery of a private bank that launders money for a "
         "ruthless crime family. When the job goes wrong they have one night to escape the "
         "city while the police and the mob close in on them.")

if not (FE and GW):
    pytest.skip("set E2E_FRONTEND_URL and E2E_GATEWAY_URL to run end-to-end tests",
                allow_module_level=True)


@pytest.fixture(scope="module")
def fe():
    with httpx.Client(base_url=FE, timeout=30) as c:
        yield c


@pytest.fixture(scope="module")
def gw():
    with httpx.Client(base_url=GW, timeout=30, headers={"X-API-Key": KEY}) as c:
        yield c


def test_ui_is_served(fe):
    r = fe.get("/")
    assert r.status_code == 200 and "What kind of film is this?" in r.text


def test_predict_through_ui_proxy(fe):
    r = fe.post("/api/gateway/api/v1/predict", json={"text": HEIST})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "Crime" in body["predicted_genres"]
    assert any(k["word"] in {"robbery", "crime", "police", "mob", "bank"} for k in body["keywords"])


def test_gateway_enforces_api_key():
    r = httpx.post(f"{GW}/api/v1/predict", json={"text": HEIST}, timeout=10)
    assert r.status_code == 401


def test_p95_latency_under_500ms(gw):
    gw.post("/api/v1/predict", json={"text": HEIST})  # warm-up
    lat = []
    for _ in range(40):
        t0 = time.perf_counter()
        assert gw.post("/api/v1/predict", json={"text": HEIST}).status_code == 200
        lat.append((time.perf_counter() - t0) * 1000)
    p95 = statistics.quantiles(lat, n=20)[-1]
    print(f"p50={statistics.median(lat):.1f}ms p95={p95:.1f}ms")
    assert p95 < 500


def test_model_info_matches_registry(gw):
    info = gw.get("/api/v1/model").json()
    assert info["version"] and info["metrics"].get("test_micro_f1", 0) >= 0.40


def test_pipeline_console_endpoints(fe):
    status = fe.get("/api/pipeline/api/v1/pipeline/status").json()
    assert status["state"] in {"idle", "running"}
    dag = fe.get("/api/pipeline/api/v1/pipeline/dag").json()
    assert len(dag["nodes"]) == 7 and dag["edges"]
    assert fe.get("/api/pipeline/api/v1/pipeline/runs").status_code == 200


def test_metrics_exposed(fe):
    assert "plotgenre_gateway_requests_total" in httpx.get(f"{GW}/metrics").text
    assert "plotgenre_frontend_proxy_requests_total" in fe.get("/metrics").text


def test_acceptance_criteria_report():
    report = json.loads((ROOT / "reports" / "metrics.json").read_text())
    assert report["test_micro_f1"] >= 0.40
    assert report["latency_p95_ms"] < 500
    assert report["acceptance_passed"] is True


def test_browser_flow():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"no browser available: {exc}")
        page = browser.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(f"{FE}/#/classify")
        assert page.locator("#predict-btn").is_disabled()
        page.click("text=Bank heist")
        page.wait_for_selector("#predicted-chips .chip", timeout=15000)
        assert "Crime" in page.inner_text("#predicted-chips")
        page.goto(f"{FE}/#/pipeline")
        page.wait_for_selector("#dag .node", timeout=15000)
        browser.close()
        # The only tolerated console error is the Grafana reachability probe.
        assert not [e for e in errors if "ERR_CONNECTION_REFUSED" not in e]
