"""Configuration helpers.

All pipeline stages read their settings from ``params.yaml`` at the project
root so that DVC can track exactly which parameters produced which outputs.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml

# Project root = three levels above this file (src/plotgenre/common/config.py).
PROJECT_ROOT = Path(os.environ.get(
    "PLOTGENRE_ROOT", Path(__file__).resolve().parents[3]))


class ConfigError(RuntimeError):
    """Raised when params.yaml is missing or a required key is absent."""


def project_path(*parts: str) -> Path:
    """Return an absolute path inside the project root."""
    return PROJECT_ROOT.joinpath(*parts)


def load_params(path: Path | None = None) -> Dict[str, Any]:
    """Load and return the full params.yaml as a dictionary.

    Args:
        path: Optional explicit path; defaults to ``<root>/params.yaml``.

    Raises:
        ConfigError: if the file does not exist or is not valid YAML.
    """
    params_file = Path(path) if path else project_path("params.yaml")
    if not params_file.exists():
        raise ConfigError(f"params file not found: {params_file}")
    try:
        with params_file.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {params_file}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{params_file} must contain a mapping at top level")
    return data


def section(name: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Return one top-level section of params.yaml (e.g. ``"train"``)."""
    params = params if params is not None else load_params()
    if name not in params:
        raise ConfigError(f"missing section '{name}' in params.yaml")
    return params[name]


def get_env(name: str, default: str | None = None) -> str | None:
    """Read a setting from the environment, falling back to ``<root>/.env``.

    The ``.env`` file is created by ``scripts/setup.sh`` and is git-ignored, so
    secrets such as the model encryption key never enter version control.
    """
    if os.environ.get(name):
        return os.environ[name]
    env_file = project_path(".env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.strip() == name:
                    return value.strip().strip('"').strip("'")
    return default


def mlflow_tracking_uri() -> str:
    """Tracking URI: env var wins, else the docker-compose MLflow server."""
    return get_env("MLFLOW_TRACKING_URI", "http://localhost:5000")
