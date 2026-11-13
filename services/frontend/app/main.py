"""PlotGenre web frontend server.

Serves the static single-page UI and a thin, allow-listed REST proxy so that

* the browser never sees the API key (it is added here, server side), and
* the UI stays an independent block that reaches the backend **only through
  configurable REST URLs** (``GATEWAY_URL``, ``PIPELINE_URL``).

It is instrumented for Prometheus as well: page loads, page-load time, UI
errors and user actions reported by the browser (``POST /telemetry``), plus
latency / status of every proxied backend call.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Literal, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s | %(levelname)-7s | frontend | %(message)s")
log = logging.getLogger("plotgenre.frontend")

STATIC = Path(__file__).resolve().parents[1] / "static"
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8000").rstrip("/")
PIPELINE_URL = os.environ.get("PIPELINE_URL", "http://localhost:8100").rstrip("/")
API_KEY = os.environ.get("API_KEY", "dev-key-change-me")
PUBLIC = {
    "grafanaUrl": os.environ.get("GRAFANA_PUBLIC_URL", "http://localhost:3000"),
    "mlflowUrl": os.environ.get("MLFLOW_PUBLIC_URL", "http://localhost:5000"),
    "prometheusUrl": os.environ.get("PROMETHEUS_PUBLIC_URL", "http://localhost:9090"),
    "alertmanagerUrl": os.environ.get("ALERTMANAGER_PUBLIC_URL", "http://localhost:9093"),
    "gatewayDocsUrl": os.environ.get("GATEWAY_PUBLIC_URL", "http://localhost:8000") + "/docs",
    "grafanaDashboardUid": os.environ.get("GRAFANA_DASHBOARD_UID", "plotgenre-main"),
}
TARGETS = {"gateway": GATEWAY_URL, "pipeline": PIPELINE_URL}
# Only these backend paths may be reached through the proxy.
ALLOWED = {
    "gateway": re.compile(r"^(health|ready|api/v1/(predict|predict/batch|model|genres|"
                          r"monitoring/drift))$"),
    "pipeline": re.compile(r"^(health|api/v1/pipeline/(status|runs|dag|reports|trigger|"
                           r"runs/[\w\-]+/log))$"),
}

PAGE_LOADS = Counter("plotgenre_frontend_page_loads", "Page views", ["page"])
PAGE_LOAD_TIME = Histogram("plotgenre_frontend_page_load_seconds", "Browser page load time",
                           ["page"], buckets=(0.1, 0.25, 0.5, 1, 2, 4, 8))
UI_ERRORS = Counter("plotgenre_frontend_ui_errors", "Errors shown to / raised in the UI",
                    ["page", "kind"])
ACTIONS = Counter("plotgenre_frontend_actions", "User actions", ["action"])
PROXY_REQ = Counter("plotgenre_frontend_proxy_requests", "Proxied backend calls",
                    ["target", "status"])
PROXY_LAT = Histogram("plotgenre_frontend_proxy_latency_seconds", "Proxied call latency",
                      ["target"], buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))

app = FastAPI(title="PlotGenre Frontend", version="1.0.0", docs_url=None, redoc_url=None)
client = httpx.AsyncClient(timeout=30)


class Telemetry(BaseModel):
    """Event reported by the browser."""

    type: Literal["page_load", "ui_error", "action"]
    page: str = Field("unknown", max_length=40, pattern=r"^[\w\-]+$")
    name: Optional[str] = Field(None, max_length=60)
    duration_ms: Optional[float] = Field(None, ge=0, le=120000)
    detail: Optional[str] = Field(None, max_length=500)


@app.get("/health")
async def health():
    """Liveness probe."""
    return {"status": "ok", "service": "frontend"}


@app.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus scrape endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/config.js")
async def config_js():
    """Runtime configuration for the browser (public URLs only, no secrets)."""
    body = f"window.PLOTGENRE_CONFIG = {json.dumps({**PUBLIC, 'apiBase': '/api'})};"
    return Response(body, media_type="application/javascript",
                    headers={"Cache-Control": "no-store"})


@app.post("/telemetry", status_code=204)
async def telemetry(event: Telemetry):
    """Record a browser event as Prometheus metrics."""
    if event.type == "page_load":
        PAGE_LOADS.labels(page=event.page).inc()
        if event.duration_ms is not None:
            PAGE_LOAD_TIME.labels(page=event.page).observe(event.duration_ms / 1000)
    elif event.type == "ui_error":
        UI_ERRORS.labels(page=event.page, kind=(event.name or "error")[:40]).inc()
        log.warning("UI error on %s: %s %s", event.page, event.name, event.detail)
    else:
        ACTIONS.labels(action=(event.name or "unknown")[:40]).inc()
    return Response(status_code=204)


@app.api_route("/api/{target}/{path:path}", methods=["GET", "POST"])
async def proxy(target: str, path: str, request: Request):
    """Forward an allow-listed call to the gateway or pipeline runner."""
    if target not in TARGETS or not ALLOWED[target].match(path):
        return JSONResponse(status_code=404, content={"error": {
            "code": "not_found", "message": "Unknown API path."}})
    url = f"{TARGETS[target]}/{path}"
    headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
    if "x-request-id" in request.headers:
        headers["X-Request-ID"] = request.headers["x-request-id"]
    start = time.perf_counter()
    try:
        resp = await client.request(request.method, url, params=request.query_params,
                                    content=await request.body(), headers=headers)
    except httpx.HTTPError as exc:
        PROXY_REQ.labels(target=target, status="unreachable").inc()
        log.error("backend %s unreachable: %s", target, exc)
        return JSONResponse(status_code=503, content={"error": {
            "code": "backend_unreachable",
            "message": f"The {target} service is not reachable. Is it running?"}})
    finally:
        PROXY_LAT.labels(target=target).observe(time.perf_counter() - start)
    PROXY_REQ.labels(target=target, status=str(resp.status_code)).inc()
    return Response(content=resp.content, status_code=resp.status_code,
                    media_type=resp.headers.get("content-type", "application/json"))


@app.get("/")
async def index():
    """Single-page app entry point."""
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
