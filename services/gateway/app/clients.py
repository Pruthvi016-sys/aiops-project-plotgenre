"""HTTP clients for the two upstream services the gateway talks to.

* :class:`ModelServerClient` - MLflow scoring server (``/ping``, ``/invocations``)
* :class:`RegistryClient`    - MLflow tracking server REST API (champion metadata)

Both are plain REST over ``httpx``; URLs come from configuration, which keeps
the gateway loosely coupled to where the model actually runs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from .metrics import UPSTREAM_ERRORS, UPSTREAM_LATENCY, UPSTREAM_UP

log = logging.getLogger("plotgenre.gateway.clients")


class UpstreamUnavailable(RuntimeError):
    """Model server could not be reached (down, restarting, timeout)."""


class UpstreamError(RuntimeError):
    """Model server answered with an error or an unexpected payload."""


class ModelServerClient:
    """Async client for the MLflow model scoring server."""

    def __init__(self, base_url: str, timeout_s: float = 10.0, retries: int = 2,
                 transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.retries = retries
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout_s,
                                         transport=transport)

    async def close(self) -> None:
        """Release the connection pool."""
        await self._client.aclose()

    async def ping(self) -> bool:
        """True if the scoring server is healthy."""
        try:
            ok = (await self._client.get("/ping", timeout=3)).status_code == 200
        except httpx.HTTPError:
            ok = False
        UPSTREAM_UP.set(1 if ok else 0)
        return ok

    async def predict(self, texts: List[str], top_k: int, explain: bool) -> List[Dict[str, Any]]:
        """Score texts; returns one dict per text with ``genres`` / ``keywords`` lists."""
        payload = {"dataframe_records": [{"text": t} for t in texts],
                   "params": {"top_k": top_k, "explain": explain}}
        last_exc: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            start = time.perf_counter()
            try:
                resp = await self._client.post("/invocations", json=payload)
                UPSTREAM_LATENCY.observe(time.perf_counter() - start)
            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
                UPSTREAM_ERRORS.labels(reason=type(exc).__name__).inc()
                UPSTREAM_UP.set(0)
                last_exc = exc
                log.warning("model server unreachable (attempt %d): %s", attempt + 1, exc)
                await asyncio.sleep(0.3 * (attempt + 1))
                continue
            if resp.status_code != 200:
                UPSTREAM_ERRORS.labels(reason=f"http_{resp.status_code}").inc()
                raise UpstreamError(f"model server returned {resp.status_code}: "
                                    f"{resp.text[:300]}")
            UPSTREAM_UP.set(1)
            return self._parse(resp.json(), len(texts))
        raise UpstreamUnavailable(f"model server unavailable: {last_exc}")

    @staticmethod
    def _parse(body: Dict[str, Any], expected: int) -> List[Dict[str, Any]]:
        """Decode the JSON-string columns produced by the pyfunc model."""
        try:
            rows = body["predictions"]
            parsed = [{"genres": json.loads(r["genres"]), "keywords": json.loads(r["keywords"]),
                       "threshold": float(r["threshold"]), "model_name": r["model_name"]}
                      for r in rows]
        except (KeyError, TypeError, ValueError) as exc:
            UPSTREAM_ERRORS.labels(reason="bad_payload").inc()
            raise UpstreamError(f"unexpected model server payload: {exc}") from exc
        if len(parsed) != expected:
            raise UpstreamError(f"expected {expected} predictions, got {len(parsed)}")
        return parsed


class RegistryClient:
    """Reads champion-model metadata from the MLflow REST API (cached)."""

    def __init__(self, base_url: str, name: str, alias: str, ttl_s: float = 30.0,
                 transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.name, self.alias, self.ttl_s = name, alias, ttl_s
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=5,
                                         transport=transport)
        self._cache: Optional[Dict[str, Any]] = None
        self._cached_at = 0.0

    async def close(self) -> None:
        """Release the connection pool."""
        await self._client.aclose()

    async def champion(self) -> Dict[str, Any]:
        """Version, run id, tags and metrics of the alias holder (empty dict if none)."""
        if self._cache is not None and time.time() - self._cached_at < self.ttl_s:
            return self._cache
        info: Dict[str, Any] = {}
        try:
            r = await self._client.get("/api/2.0/mlflow/registered-models/alias",
                                       params={"name": self.name, "alias": self.alias})
            if r.status_code == 200:
                mv = r.json()["model_version"]
                tags = {t["key"]: t["value"] for t in mv.get("tags", [])}
                info = {"version": mv.get("version"), "run_id": mv.get("run_id"),
                        "algorithm": tags.get("best_model"),
                        "data_version": tags.get("data_version"),
                        "git_commit": tags.get("git_commit"), "metrics": {}}
                run = await self._client.get("/api/2.0/mlflow/runs/get",
                                             params={"run_id": mv.get("run_id")})
                if run.status_code == 200:
                    data = run.json()["run"]
                    info["experiment_id"] = data["info"].get("experiment_id")
                    info["metrics"] = {m["key"]: m["value"]
                                       for m in data["data"].get("metrics", [])
                                       if m["key"].startswith(("test_", "best_val_"))}
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.warning("could not read model registry: %s", exc)
            return self._cache or {}
        self._cache, self._cached_at = info, time.time()
        return info
