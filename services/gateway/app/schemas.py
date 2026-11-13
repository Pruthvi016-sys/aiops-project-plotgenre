"""Pydantic request / response models - the API contract documented in docs/LLD.md."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    """Single plot summary to classify."""

    text: str = Field(..., description="Plot summary in English (5+ words).",
                      examples=["A retired hitman is pulled back into the criminal underworld "
                                "when gangsters kill his dog."])
    top_k: int = Field(3, ge=1, le=12, description="Max genres to explain.")
    explain: bool = Field(True, description="Return influential keywords.")


class BatchPredictRequest(BaseModel):
    """Several plot summaries at once."""

    texts: List[str] = Field(..., min_length=1, description="1..MAX_BATCH plot summaries.")
    top_k: int = Field(3, ge=1, le=12)
    explain: bool = Field(False)


class GenreScore(BaseModel):
    """Confidence for one genre."""

    genre: str
    confidence: float = Field(..., ge=0, le=1)
    predicted: bool


class Keyword(BaseModel):
    """A word that pushed the model towards a genre."""

    word: str
    genre: str
    weight: float


class ModelMeta(BaseModel):
    """Which model produced the prediction."""

    name: str
    version: Optional[str] = None
    algorithm: Optional[str] = None
    threshold: Optional[float] = None


class PredictResponse(BaseModel):
    """Prediction for one plot summary."""

    request_id: str
    predicted_genres: List[str]
    genres: List[GenreScore]
    keywords: List[Keyword]
    model: ModelMeta
    latency_ms: float
    warnings: List[str] = []


class BatchPredictResponse(BaseModel):
    """Predictions for a batch."""

    request_id: str
    count: int
    results: List[PredictResponse]
    latency_ms: float


class HealthResponse(BaseModel):
    """Liveness / readiness."""

    status: str
    service: str = "gateway"
    version: str
    model_server: Optional[str] = None


class ModelInfoResponse(BaseModel):
    """Champion model details pulled from the MLflow registry."""

    name: str
    alias: str
    version: Optional[str]
    run_id: Optional[str]
    algorithm: Optional[str]
    data_version: Optional[str]
    git_commit: Optional[str]
    metrics: dict = {}
    mlflow_run_url: Optional[str] = None


class DriftResponse(BaseModel):
    """Live drift statistics over the recent request window."""

    window_size: int
    window_capacity: int
    drift_score: Optional[float]
    label_drift: Optional[float]
    threshold: Optional[float]
    drift_detected: bool
    reference_loaded: bool
    reference_data_version: Optional[str] = None


class ErrorBody(BaseModel):
    """Error envelope used by every non-2xx response."""

    code: str
    message: str
    request_id: Optional[str] = None


class ErrorResponse(BaseModel):
    """Top-level error response."""

    error: ErrorBody
