"""Pipeline run tracking for the Pipeline management console.

Every DVC stage runs inside :func:`track_stage`. It records

* a JSON line in ``reports/pipeline_runs.jsonl`` (status, duration, rows,
  throughput, error message) - the run history shown in the UI, and
* Prometheus metrics pushed to the Pushgateway (if reachable) so Grafana can
  plot pipeline throughput, duration and failures in near real time.

A pipeline "run id" groups the stages of one ``dvc repro``; it is taken from
``PIPELINE_RUN_ID`` (set by the pipeline-runner service) or generated.
"""

from __future__ import annotations

import json
import os
import time
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator

from plotgenre.common.config import project_path
from plotgenre.common.logging_utils import get_logger

log = get_logger(__name__, project_path("logs", "pipeline.log"))

RUNS_FILE = project_path("reports", "pipeline_runs.jsonl")
_RUN_ID = os.environ.get("PIPELINE_RUN_ID") or (
    datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6])


class StageContext:
    """Mutable record a stage fills in (rows processed, extra info)."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        self.rows = 0
        self.extra: Dict[str, Any] = {}

    def set_rows(self, rows: int) -> None:
        """Record how many rows/items the stage processed."""
        self.rows = int(rows)

    def add(self, **kwargs: Any) -> None:
        """Attach extra key/values to the run record."""
        self.extra.update(kwargs)


def _append_record(record: Dict[str, Any]) -> None:
    RUNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with RUNS_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


def _push_metrics(record: Dict[str, Any]) -> None:
    """Push stage metrics to the Prometheus Pushgateway; never fails the stage."""
    gateway = os.environ.get("PUSHGATEWAY_URL", "localhost:9091")
    if os.environ.get("DISABLE_PUSHGATEWAY") == "1":
        return
    try:
        from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

        registry = CollectorRegistry()
        labels = ["stage"]
        Gauge("plotgenre_pipeline_stage_duration_seconds", "Stage wall time",
              labels, registry=registry).labels(record["stage"]).set(record["duration_s"])
        Gauge("plotgenre_pipeline_stage_rows", "Rows processed by stage",
              labels, registry=registry).labels(record["stage"]).set(record["rows"])
        Gauge("plotgenre_pipeline_stage_throughput_rows_per_second", "Stage throughput",
              labels, registry=registry).labels(record["stage"]).set(record["throughput_rps"])
        Gauge("plotgenre_pipeline_stage_success", "1 if last run succeeded else 0",
              labels, registry=registry).labels(record["stage"]).set(
                  1 if record["status"] == "success" else 0)
        Gauge("plotgenre_pipeline_stage_last_run_timestamp", "Unix time of last run",
              labels, registry=registry).labels(record["stage"]).set(time.time())
        for key, value in record.get("extra", {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                Gauge(f"plotgenre_pipeline_{key}", f"Stage metric {key}", labels,
                      registry=registry).labels(record["stage"]).set(value)
        push_to_gateway(gateway, job=f"plotgenre_{record['stage']}", registry=registry,
                        timeout=3)
    except Exception as exc:  # noqa: BLE001 - monitoring must not break the pipeline
        log.debug("pushgateway unavailable (%s); metrics kept in run log only", exc)


@contextmanager
def track_stage(stage: str) -> Iterator[StageContext]:
    """Context manager that times a stage and records success or failure."""
    ctx = StageContext(stage)
    started = time.time()
    log.info("stage '%s' started (pipeline run %s)", stage, _RUN_ID)
    status, error = "success", None
    try:
        yield ctx
    except Exception as exc:
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
        log.error("stage '%s' failed: %s\n%s", stage, error, traceback.format_exc())
        raise
    finally:
        duration = max(time.time() - started, 1e-9)
        record = {
            "pipeline_run_id": _RUN_ID,
            "stage": stage,
            "status": status,
            "started_at": datetime.fromtimestamp(started, timezone.utc).isoformat(),
            "duration_s": round(duration, 3),
            "rows": ctx.rows,
            "throughput_rps": round(ctx.rows / duration, 2) if ctx.rows else 0.0,
            "error": error,
            "extra": ctx.extra,
        }
        _append_record(record)
        _push_metrics(record)
        log.info("stage '%s' %s in %.2fs (%d rows, %.1f rows/s)", stage, status,
                 duration, ctx.rows, record["throughput_rps"])
