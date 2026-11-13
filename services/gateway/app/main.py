"""PlotGenre API gateway (FastAPI).

The gateway is the only backend the UI talks to. It

* authenticates callers (``X-API-Key``),
* validates input and turns it into a call to the MLflow model server,
* reshapes the model output into the documented API contract,
* records Prometheus metrics (traffic, latency, errors, upstream health,
  predicted-genre distribution, live data drift),
* returns uniform JSON errors.

Run locally: ``uvicorn gateway.app.main:app --port 8000`` (PYTHONPATH=services:src)
OpenAPI docs: ``http://localhost:8000/docs``
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import List

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.security import APIKeyHeader
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .clients import ModelServerClient, RegistryClient, UpstreamError, UpstreamUnavailable
from .config import Settings, get_settings
from .drift_monitor import DriftMonitor
from .metrics import (BUILD_INFO, ERRORS, IN_PROGRESS, INPUT_WORDS, LATENCY, MODEL_INFO,
                      PREDICTED_GENRE, PREDICTIONS, REQUESTS, TOP_CONFIDENCE)
from .schemas import (BatchPredictRequest, BatchPredictResponse, DriftResponse, ErrorResponse,
                      HealthResponse, ModelInfoResponse, ModelMeta, PredictRequest,
                      PredictResponse)

VERSION = "1.0.0"
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
log = logging.getLogger("plotgenre.gateway")


class APIError(Exception):
    """Application error rendered as the standard error envelope."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create upstream clients once per process and close them on shutdown."""
    settings: Settings = app.dependency_overrides.get(get_settings, get_settings)()
    app.state.model = ModelServerClient(settings.model_server_url, settings.upstream_timeout_s,
                                        settings.upstream_retries)
    app.state.registry = RegistryClient(settings.mlflow_url, settings.model_name,
                                        settings.model_alias)
    app.state.drift = DriftMonitor(settings.drift_reference_path)
    BUILD_INFO.info({"version": VERSION, "model_server": settings.model_server_url})
    log.info("gateway started; model server=%s mlflow=%s", settings.model_server_url,
             settings.mlflow_url)
    yield
    await app.state.model.close()
    await app.state.registry.close()


app = FastAPI(title="PlotGenre Gateway", version=VERSION, lifespan=lifespan,
              description="REST API that predicts movie genres from plot summaries. "
                          "Protected endpoints need the `X-API-Key` header.",
              responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse},
                         503: {"model": ErrorResponse}})
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins,
                   allow_methods=["GET", "POST"], allow_headers=["*"])

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str = Depends(api_key_header),
                    settings: Settings = Depends(get_settings)) -> str:
    """Reject requests without a valid ``X-API-Key`` header."""
    if not key or key not in settings.api_keys:
        raise APIError(401, "unauthorized", "Missing or invalid API key (X-API-Key header).")
    return key


# --------------------------------------------------------------------------- middleware
@app.middleware("http")
async def observe(request: Request, call_next):
    """Request id, structured access log and RED metrics for every request."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    endpoint = request.url.path
    IN_PROGRESS.inc()
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        route = request.scope.get("route")
        endpoint = getattr(route, "path", endpoint)
        elapsed = time.perf_counter() - start
        IN_PROGRESS.dec()
        if endpoint != "/metrics":
            REQUESTS.labels(endpoint=endpoint, method=request.method, status=str(status)).inc()
            LATENCY.labels(endpoint=endpoint).observe(elapsed)
            log.info("%s %s -> %s in %.1fms [%s]", request.method, endpoint, status,
                     elapsed * 1000, request_id)


def _error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    ERRORS.labels(endpoint=request.url.path, type=code).inc()
    return JSONResponse(status_code=status, content={"error": {
        "code": code, "message": message,
        "request_id": getattr(request.state, "request_id", None)}})


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError):
    """Render :class:`APIError`."""
    return _error(request, exc.status, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    """Turn pydantic errors into one friendly sentence."""
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", [])[1:]) or "body"
    return _error(request, 422, "invalid_input", f"{field}: {first.get('msg', 'invalid')}")


@app.exception_handler(UpstreamUnavailable)
async def upstream_down_handler(request: Request, exc: UpstreamUnavailable):
    """Model server down or restarting (e.g. during a redeploy)."""
    log.error("upstream unavailable: %s", exc)
    return _error(request, 503, "model_unavailable",
                  "The prediction service is starting or temporarily unavailable. "
                  "Please try again in a few seconds.")


@app.exception_handler(UpstreamError)
async def upstream_error_handler(request: Request, exc: UpstreamError):
    """Model server returned an error."""
    log.error("upstream error: %s", exc)
    return _error(request, 502, "model_error", "The model could not process this request.")


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    """Last-resort handler so clients always get JSON."""
    log.exception("unhandled error: %s", exc)
    return _error(request, 500, "internal_error", "Unexpected server error.")


# --------------------------------------------------------------------------- helpers
def validate_text(text: str, settings: Settings) -> List[str]:
    """Raise APIError for unusable text; return non-fatal warnings."""
    stripped = (text or "").strip()
    if not stripped:
        raise APIError(422, "empty_text", "Please enter a plot summary.")
    if len(stripped) > settings.max_chars:
        raise APIError(422, "text_too_long",
                       f"Plot summary is too long (max {settings.max_chars} characters).")
    words = stripped.split()
    if len(words) < settings.min_words:
        raise APIError(422, "text_too_short",
                       f"Please write at least {settings.min_words} words about the plot.")
    warnings = []
    if len(words) < settings.warn_words:
        warnings.append(f"Short summary ({len(words)} words): predictions are more reliable "
                        f"with {settings.warn_words}+ words.")
    letters = sum(c.isascii() and c.isalpha() for c in stripped)
    if letters / max(sum(c.isalpha() for c in stripped), 1) < 0.7:
        warnings.append("The text does not look like English; the model was trained on "
                        "English plot summaries.")
    return warnings


async def _model_meta(request: Request, threshold: float, name: str) -> ModelMeta:
    info = await request.app.state.registry.champion()
    if info.get("version"):
        MODEL_INFO.info({"version": str(info["version"]), "algorithm": name})
    return ModelMeta(name=get_settings().model_name, version=info.get("version"),
                     algorithm=name, threshold=threshold)


def _record(request: Request, text: str, result: dict) -> List[str]:
    predicted = [g["genre"] for g in result["genres"] if g["predicted"]]
    for genre in predicted:
        PREDICTED_GENRE.labels(genre=genre).inc()
    if result["genres"]:
        TOP_CONFIDENCE.observe(result["genres"][0]["confidence"])
    INPUT_WORDS.observe(len(text.split()))
    PREDICTIONS.inc()
    request.app.state.drift.observe(text, predicted)
    return predicted


# --------------------------------------------------------------------------- routes
@app.get("/health", response_model=HealthResponse, tags=["ops"])
async def health() -> HealthResponse:
    """Liveness probe (no auth)."""
    return HealthResponse(status="ok", version=VERSION)


@app.get("/ready", response_model=HealthResponse, tags=["ops"],
         responses={503: {"model": HealthResponse}})
async def ready(request: Request):
    """Readiness probe: is the model server reachable?"""
    ok = await request.app.state.model.ping()
    body = HealthResponse(status="ready" if ok else "not_ready", version=VERSION,
                          model_server="up" if ok else "down")
    return JSONResponse(status_code=200 if ok else 503, content=body.model_dump())


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Prometheus scrape endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/v1/genres", response_model=List[str], tags=["prediction"])
async def genres(request: Request) -> List[str]:
    """Genres the model can predict."""
    prior = request.app.state.drift.prior
    return sorted(prior) if prior else []


@app.post("/api/v1/predict", response_model=PredictResponse, tags=["prediction"],
          dependencies=[Depends(require_api_key)])
async def predict(body: PredictRequest, request: Request,
                  settings: Settings = Depends(get_settings)) -> PredictResponse:
    """Predict ranked genres + influential keywords for one plot summary."""
    start = time.perf_counter()
    warnings = validate_text(body.text, settings)
    text = body.text.strip()
    result = (await request.app.state.model.predict([text], body.top_k, body.explain))[0]
    predicted = _record(request, text, result)
    meta = await _model_meta(request, result["threshold"], result["model_name"])
    return PredictResponse(request_id=request.state.request_id, predicted_genres=predicted,
                           genres=result["genres"], keywords=result["keywords"], model=meta,
                           latency_ms=round((time.perf_counter() - start) * 1000, 2),
                           warnings=warnings)


@app.post("/api/v1/predict/batch", response_model=BatchPredictResponse, tags=["prediction"],
          dependencies=[Depends(require_api_key)])
async def predict_batch(body: BatchPredictRequest, request: Request,
                        settings: Settings = Depends(get_settings)) -> BatchPredictResponse:
    """Predict genres for up to ``MAX_BATCH`` plot summaries in one call."""
    start = time.perf_counter()
    if len(body.texts) > settings.max_batch:
        raise APIError(422, "batch_too_large", f"At most {settings.max_batch} texts per batch.")
    warnings = [validate_text(t, settings) for t in body.texts]
    texts = [t.strip() for t in body.texts]
    results = await request.app.state.model.predict(texts, body.top_k, body.explain)
    out = []
    for text, res, warn in zip(texts, results, warnings):
        predicted = _record(request, text, res)
        meta = await _model_meta(request, res["threshold"], res["model_name"])
        out.append(PredictResponse(request_id=request.state.request_id,
                                   predicted_genres=predicted, genres=res["genres"],
                                   keywords=res["keywords"], model=meta, latency_ms=0.0,
                                   warnings=warn))
    return BatchPredictResponse(request_id=request.state.request_id, count=len(out),
                                results=out,
                                latency_ms=round((time.perf_counter() - start) * 1000, 2))


@app.get("/api/v1/model", response_model=ModelInfoResponse, tags=["model"],
         dependencies=[Depends(require_api_key)])
async def model_info(request: Request,
                     settings: Settings = Depends(get_settings)) -> ModelInfoResponse:
    """Champion model metadata from the MLflow Model Registry."""
    info = await request.app.state.registry.champion()
    public_mlflow = os.environ.get("MLFLOW_PUBLIC_URL", "http://localhost:5000")
    url = (f"{public_mlflow}/#/experiments/{info['experiment_id']}/runs/{info['run_id']}"
           if info.get("run_id") and info.get("experiment_id") else None)
    return ModelInfoResponse(name=settings.model_name, alias=settings.model_alias,
                             version=info.get("version"), run_id=info.get("run_id"),
                             algorithm=info.get("algorithm"),
                             data_version=info.get("data_version"),
                             git_commit=info.get("git_commit"),
                             metrics=info.get("metrics", {}), mlflow_run_url=url)


@app.get("/api/v1/monitoring/drift", response_model=DriftResponse, tags=["monitoring"],
         dependencies=[Depends(require_api_key)])
async def drift(request: Request) -> DriftResponse:
    """Live drift statistics over the most recent requests."""
    request.app.state.drift.reload()
    return DriftResponse(**request.app.state.drift.snapshot())
