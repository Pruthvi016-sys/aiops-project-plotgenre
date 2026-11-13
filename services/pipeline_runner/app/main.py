"""Pipeline runner - the pipeline management console backend (FastAPI).

Responsibilities
----------------
* Run the DVC pipeline (``dvc repro``) on demand, from the UI or from an
  Alertmanager webhook when data drift is detected (automatic retraining).
* Keep a history of pipeline runs (trigger, reason, status, duration, logs)
  and expose per-stage results recorded by the stages themselves
  (``reports/pipeline_runs.jsonl``).
* Serve the DVC DAG, the latest reports and ``dvc status`` to the UI.
* Export Prometheus metrics about pipeline runs.

The runner works on the project directory mounted at ``PROJECT_DIR``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from pydantic import BaseModel, Field

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s | %(levelname)-7s | pipeline-runner | %(message)s")
log = logging.getLogger("plotgenre.runner")

PROJECT_DIR = Path(os.environ.get("PROJECT_DIR", Path(__file__).resolve().parents[3]))
API_KEYS = [k.strip() for k in os.environ.get(
    "API_KEYS", os.environ.get("API_KEY", "dev-key-change-me")).split(",") if k.strip()]
COOLDOWN_S = int(os.environ.get("RETRAIN_COOLDOWN_S", "1800"))
DVC_PUSH = os.environ.get("RUNNER_DVC_PUSH", "1") == "1"
DRIFT_ALERTS = {a.strip() for a in os.environ.get(
    "DRIFT_ALERT_NAMES", "PlotGenreDataDrift,PlotGenreLiveInputDrift").split(",") if a.strip()}
REPORTS = PROJECT_DIR / "reports"
GROUP_GAP_S = 90
RUNS_DB = REPORTS / "runner_runs.json"
LOG_DIR = PROJECT_DIR / "logs" / "runs"
REPORT_FILES = ("data_quality", "split_summary", "featurize_summary", "train_metrics",
                "metrics", "drift_report")

RUNS = Counter("plotgenre_pipeline_runs", "Pipeline runs by outcome", ["status", "trigger"])
RUNNING = Gauge("plotgenre_pipeline_running", "1 while a pipeline run is in progress")
LAST_DURATION = Gauge("plotgenre_pipeline_last_duration_seconds", "Duration of last run")
LAST_SUCCESS = Gauge("plotgenre_pipeline_last_success_timestamp",
                     "Unix time of the last successful run")
LAST_STATUS = Gauge("plotgenre_pipeline_last_run_success", "1 if last run succeeded")
ALERTS = Counter("plotgenre_pipeline_alerts_received", "Alertmanager notifications",
                 ["alertname", "action"])


class TriggerRequest(BaseModel):
    """Body of ``POST /api/v1/pipeline/trigger``."""

    reason: str = Field("manual run from UI", max_length=200)
    data_version: Optional[str] = Field(None, pattern="^v[12]$",
                                        description="Switch data version before running.")
    force: bool = Field(False, description="Re-run all stages (dvc repro -f).")


class Runner:
    """Serialises pipeline executions and persists their history."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.current: Optional[Dict[str, Any]] = None
        self.history: List[Dict[str, Any]] = self._load()
        self.last_auto_trigger = 0.0

    # ------------------------------------------------------------------ persistence
    def _load(self) -> List[Dict[str, Any]]:
        try:
            return json.loads(RUNS_DB.read_text())
        except (OSError, json.JSONDecodeError):
            return []

    def _save(self) -> None:
        REPORTS.mkdir(parents=True, exist_ok=True)
        RUNS_DB.write_text(json.dumps(self.history[-200:], indent=2))

    # ------------------------------------------------------------------ execution
    @property
    def running(self) -> bool:
        """True while a run is in progress."""
        return self.current is not None

    def start(self, trigger: str, reason: str, data_version: Optional[str] = None,
              force: bool = False) -> Dict[str, Any]:
        """Start a background run; raise if one is already running."""
        with self.lock:
            if self.current:
                raise HTTPException(409, detail={"code": "already_running",
                                                 "message": "A pipeline run is in progress.",
                                                 "run_id": self.current["run_id"]})
            run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + \
                uuid.uuid4().hex[:6]
            self.current = {"run_id": run_id, "trigger": trigger, "reason": reason,
                            "status": "running", "force": force,
                            "started_at": datetime.now(timezone.utc).isoformat(),
                            "data_version": data_version or current_data_version()}
            RUNNING.set(1)
        threading.Thread(target=self._execute, args=(dict(self.current),), daemon=True).start()
        log.info("pipeline run %s started (%s: %s)", run_id, trigger, reason)
        return self.current

    def _execute(self, run: Dict[str, Any]) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOG_DIR / f"{run['run_id']}.log"
        env = {**os.environ, "PIPELINE_RUN_ID": run["run_id"]}
        started = time.time()
        code = -1
        try:
            if run["data_version"] != current_data_version():
                set_data_version(run["data_version"])
            cmds = [["dvc", "repro"] + (["-f"] if run["force"] else [])]
            if DVC_PUSH:
                cmds.append(["dvc", "push"])
            with log_path.open("w", encoding="utf-8") as out:
                for cmd in cmds:
                    out.write(f"$ {' '.join(cmd)}\n")
                    out.flush()
                    code = subprocess.run(cmd, cwd=PROJECT_DIR, env=env, stdout=out,  # noqa: S603
                                          stderr=subprocess.STDOUT, check=False).returncode
                    if code != 0:
                        break
        except Exception as exc:  # noqa: BLE001 - record any failure in the history
            log.exception("pipeline run %s crashed", run["run_id"])
            with log_path.open("a", encoding="utf-8") as out:
                out.write(f"\nrunner error: {exc}\n")
        duration = time.time() - started
        status = "success" if code == 0 else "failed"
        run.update(status=status, exit_code=code, duration_s=round(duration, 1),
                   finished_at=datetime.now(timezone.utc).isoformat())
        RUNS.labels(status=status, trigger=run["trigger"]).inc()
        LAST_DURATION.set(duration)
        LAST_STATUS.set(1 if code == 0 else 0)
        if code == 0:
            LAST_SUCCESS.set(time.time())
        with self.lock:
            self.history.append(run)
            self._save()
            self.current = None
            RUNNING.set(0)
        log.info("pipeline run %s finished: %s in %.1fs", run["run_id"], status, duration)


runner = Runner()
app = FastAPI(title="PlotGenre Pipeline Runner", version="1.0.0",
              description="Pipeline management console API (DVC orchestration).")


# ---------------------------------------------------------------------- helpers
def require_api_key(x_api_key: Optional[str] = Header(None),
                    authorization: Optional[str] = Header(None)) -> None:
    """Accept ``X-API-Key`` (UI) or ``Authorization: Bearer`` (Alertmanager)."""
    token = x_api_key or (authorization or "").removeprefix("Bearer ").strip()
    if token not in API_KEYS:
        raise HTTPException(401, detail={"code": "unauthorized",
                                         "message": "Missing or invalid API key."})


def current_data_version() -> str:
    """data_version from params.yaml."""
    try:
        params = yaml.safe_load((PROJECT_DIR / "params.yaml").read_text())
        return params["split"]["data_version"]
    except (OSError, KeyError, TypeError, yaml.YAMLError):
        return "unknown"


def set_data_version(version: str) -> None:
    """Edit ``split.data_version`` in params.yaml, preserving comments."""
    path = PROJECT_DIR / "params.yaml"
    text = path.read_text()
    new, n = re.subn(r"(?m)^(\s*data_version:\s*)v\d+", rf"\g<1>{version}", text, count=1)
    if n != 1:
        raise RuntimeError("could not find split.data_version in params.yaml")
    path.write_text(new)
    log.info("params.yaml: data_version -> %s", version)


def stage_records(limit: int = 2000) -> List[Dict[str, Any]]:
    """Per-stage records written by the stages (newest last)."""
    path = REPORTS / "pipeline_runs.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def read_dag() -> Dict[str, Any]:
    """Nodes/edges of the DVC pipeline derived from dvc.yaml (deps -> outs)."""
    spec = yaml.safe_load((PROJECT_DIR / "dvc.yaml").read_text())["stages"]

    def paths(items):
        for item in items or []:
            yield next(iter(item)) if isinstance(item, dict) else item

    produced = {}
    for name, st in spec.items():
        for key in ("outs", "metrics", "plots"):
            for p in paths(st.get(key)):
                produced[p] = name
    last = {}
    for rec in stage_records():
        last[rec["stage"]] = rec
    nodes, edges = [], set()
    for name, st in spec.items():
        rec = last.get(name, {})
        nodes.append({"id": name, "cmd": st.get("cmd"), "status": rec.get("status", "never_run"),
                      "duration_s": rec.get("duration_s"), "rows": rec.get("rows"),
                      "throughput_rps": rec.get("throughput_rps"),
                      "last_run": rec.get("started_at"),
                      "params": [p if isinstance(p, str) else next(iter(p))
                                 for p in st.get("params", [])]})
        for dep in paths(st.get("deps")):
            src = produced.get(dep)
            if src and src != name:
                edges.add((src, name))
    return {"nodes": nodes, "edges": [{"from": a, "to": b} for a, b in sorted(edges)]}


def dvc_status() -> Dict[str, Any]:
    """``dvc status --json``: which stages are out of date."""
    try:
        res = subprocess.run(["dvc", "status", "--json"], cwd=PROJECT_DIR,  # noqa: S603,S607
                             capture_output=True, text=True, timeout=60, check=False)
        data = json.loads(res.stdout or "{}")
        return {"up_to_date": not data, "changed_stages": sorted(data.keys())}
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return {"up_to_date": None, "error": str(exc)}


# ---------------------------------------------------------------------- routes
@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    """Uniform error envelope."""
    if isinstance(exc.detail, dict):
        detail = exc.detail
    else:
        detail = {"code": "error", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


@app.get("/health")
def health() -> Dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "service": "pipeline-runner"}


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    """Prometheus scrape endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/v1/pipeline/status")
def status(check_dvc: bool = Query(False, description="Also run `dvc status` (slower).")):
    """Current state, last run, per-stage health and data version."""
    last = runner.history[-1] if runner.history else None
    stages = {n["id"]: n["status"] for n in read_dag()["nodes"]}
    body = {"state": "running" if runner.running else "idle", "current_run": runner.current,
            "last_run": last, "data_version": current_data_version(), "stages": stages,
            "totals": {"runs": len(runner.history),
                       "success": sum(r["status"] == "success" for r in runner.history),
                       "failed": sum(r["status"] == "failed" for r in runner.history)}}
    if check_dvc:
        body["dvc"] = dvc_status()
    return body


@app.get("/api/v1/pipeline/runs")
def runs(limit: int = Query(20, ge=1, le=200)):
    """Run history (newest first) with the stage results of each run."""
    by_run: Dict[str, List[Dict[str, Any]]] = {}
    for rec in stage_records():
        by_run.setdefault(rec["pipeline_run_id"], []).append(rec)
    history = list(reversed(runner.history))[:limit]
    known = {r["run_id"] for r in runner.history}
    items = [{**r, "stages": by_run.get(r["run_id"], [])} for r in history]
    # Stage runs started outside the runner (e.g. `dvc repro` in a terminal):
    # each stage is its own process, so group records that follow each other
    # within GROUP_GAP_S seconds into one pipeline run.
    loose = sorted((r for run_id, recs in by_run.items() if run_id not in known for r in recs),
                   key=lambda r: r["started_at"])
    groups: List[List[Dict[str, Any]]] = []
    prev_end = None
    for rec in loose:
        start = datetime.fromisoformat(rec["started_at"]).timestamp()
        if groups and prev_end is not None and start - prev_end <= GROUP_GAP_S:
            groups[-1].append(rec)
        else:
            groups.append([rec])
        prev_end = start + rec["duration_s"]
    external = []
    for recs in groups:
        status_ = "failed" if any(r["status"] == "failed" for r in recs) else "success"
        external.append({"run_id": recs[0]["pipeline_run_id"], "trigger": "cli",
                         "reason": "dvc repro (terminal)", "status": status_,
                         "started_at": recs[0]["started_at"],
                         "duration_s": round(sum(r["duration_s"] for r in recs), 1),
                         "stages": recs})
    items.extend(sorted(external, key=lambda r: r["started_at"], reverse=True))
    items.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    if runner.current:
        items.insert(0, {**runner.current, "stages": by_run.get(runner.current["run_id"], [])})
    return {"count": len(items[:limit]), "runs": items[:limit]}


@app.get("/api/v1/pipeline/runs/{run_id}/log")
def run_log(run_id: str, tail: int = Query(200, ge=10, le=5000)):
    """Last lines of the console output of a runner-started run."""
    if not re.fullmatch(r"[\w\-]+", run_id):
        raise HTTPException(400, detail={"code": "bad_run_id", "message": "Invalid run id."})
    path = LOG_DIR / f"{run_id}.log"
    if not path.exists():
        raise HTTPException(404, detail={"code": "not_found", "message": "No log for this run."})
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-tail:]
    return {"run_id": run_id, "lines": lines}


@app.get("/api/v1/pipeline/dag")
def dag():
    """DVC DAG with the latest status of every stage."""
    return read_dag()


@app.get("/api/v1/pipeline/reports")
def reports():
    """Latest JSON reports produced by the stages."""
    out = {}
    for name in REPORT_FILES:
        path = REPORTS / f"{name}.json"
        try:
            out[name] = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            out[name] = None
    return out


@app.post("/api/v1/pipeline/trigger", status_code=202, dependencies=[Depends(require_api_key)])
def trigger(body: TriggerRequest):
    """Start ``dvc repro`` in the background."""
    return runner.start("manual", body.reason, body.data_version, body.force)


@app.post("/api/v1/alerts", dependencies=[Depends(require_api_key)])
def alertmanager_webhook(payload: Dict[str, Any]):
    """Alertmanager webhook: a firing drift alert triggers retraining on data v2."""
    actions = []
    for alert in payload.get("alerts", []):
        name = alert.get("labels", {}).get("alertname", "unknown")
        if name not in DRIFT_ALERTS or alert.get("status") != "firing":
            ALERTS.labels(alertname=name, action="ignored").inc()
            actions.append({"alert": name, "action": "ignored"})
            continue
        if runner.running or time.time() - runner.last_auto_trigger < COOLDOWN_S:
            ALERTS.labels(alertname=name, action="cooldown").inc()
            actions.append({"alert": name, "action": "skipped (running or cooldown)"})
            continue
        runner.last_auto_trigger = time.time()
        summary = alert.get("annotations", {}).get("summary", "")
        run = runner.start("drift_alert", f"{name}: {summary}", data_version="v2")
        ALERTS.labels(alertname=name, action="retrain").inc()
        actions.append({"alert": name, "action": "retrain", "run_id": run["run_id"]})
    return {"received": len(payload.get("alerts", [])), "actions": actions}
