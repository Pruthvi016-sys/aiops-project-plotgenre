"""Gateway settings - everything is configurable through environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


def _list(value: str) -> List[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    """Immutable runtime configuration of the gateway."""

    model_server_url: str = field(default_factory=lambda: os.environ.get(
        "MODEL_SERVER_URL", "http://localhost:5001"))
    mlflow_url: str = field(default_factory=lambda: os.environ.get(
        "MLFLOW_TRACKING_URI", "http://localhost:5000"))
    model_name: str = field(default_factory=lambda: os.environ.get(
        "MODEL_NAME", "plotgenre-classifier"))
    model_alias: str = field(default_factory=lambda: os.environ.get("MODEL_ALIAS", "champion"))
    api_keys: List[str] = field(default_factory=lambda: _list(os.environ.get(
        "API_KEYS", os.environ.get("API_KEY", "dev-key-change-me"))))
    upstream_timeout_s: float = field(default_factory=lambda: float(os.environ.get(
        "UPSTREAM_TIMEOUT_S", "10")))
    upstream_retries: int = field(default_factory=lambda: int(os.environ.get(
        "UPSTREAM_RETRIES", "2")))
    drift_reference_path: str = field(default_factory=lambda: os.environ.get(
        "DRIFT_REFERENCE_PATH", "reports/drift_reference.json"))
    cors_origins: List[str] = field(default_factory=lambda: _list(os.environ.get(
        "CORS_ORIGINS", "http://localhost:8080")))
    min_words: int = field(default_factory=lambda: int(os.environ.get("MIN_WORDS", "5")))
    warn_words: int = field(default_factory=lambda: int(os.environ.get("WARN_WORDS", "30")))
    max_chars: int = field(default_factory=lambda: int(os.environ.get("MAX_CHARS", "20000")))
    max_batch: int = field(default_factory=lambda: int(os.environ.get("MAX_BATCH", "50")))


def get_settings() -> Settings:
    """Factory used with FastAPI dependency injection (overridable in tests)."""
    return Settings()
