"""Pipeline-runner console API on a temporary project directory."""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def runner_app(tmp_path, monkeypatch):
    from pipeline_runner.app import main as rm

    shutil.copy(ROOT / "dvc.yaml", tmp_path / "dvc.yaml")
    shutil.copy(ROOT / "params.yaml", tmp_path / "params.yaml")
    (tmp_path / "params.yaml").write_text(  # start every test from data version v1
        (tmp_path / "params.yaml").read_text().replace("data_version: v2", "data_version: v1"))
    (tmp_path / "reports").mkdir()
    recs = [{"pipeline_run_id": "r1", "stage": s, "status": "success", "duration_s": 1.0,
             "started_at": f"2026-01-01T00:00:0{i}+00:00", "rows": 10, "throughput_rps": 10.0,
             "error": None, "extra": {}} for i, s in enumerate(["ingest", "preprocess"])]
    recs.append({**recs[0], "pipeline_run_id": "r2", "stage": "split",
                 "started_at": "2026-01-01T00:00:05+00:00", "status": "failed", "error": "X"})
    (tmp_path / "reports" / "pipeline_runs.jsonl").write_text(
        "\n".join(json.dumps(r) for r in recs))
    (tmp_path / "reports" / "metrics.json").write_text('{"test_micro_f1": 0.6}')
    monkeypatch.setattr(rm, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(rm, "REPORTS", tmp_path / "reports")
    monkeypatch.setattr(rm, "RUNS_DB", tmp_path / "reports" / "runner_runs.json")
    monkeypatch.setattr(rm, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(rm, "API_KEYS", ["test-key"])
    rm.runner.history, rm.runner.current, rm.runner.last_auto_trigger = [], None, 0.0
    started = []
    monkeypatch.setattr(rm.runner, "start", lambda trig, reason, data_version=None, force=False:
                        started.append((trig, reason, data_version)) or {"run_id": "x", "trigger": trig})
    return TestClient(rm.app), rm, tmp_path, started


def test_dag_matches_dvc_yaml(runner_app):
    client, *_ = runner_app
    dag = client.get("/api/v1/pipeline/dag").json()
    ids = [n["id"] for n in dag["nodes"]]
    assert ids[:2] == ["ingest", "preprocess"] and "drift_check" in ids
    edges = {(e["from"], e["to"]) for e in dag["edges"]}
    assert {("ingest", "preprocess"), ("featurize", "train"), ("train", "evaluate"),
            ("preprocess", "drift_check")} <= edges
    status = {n["id"]: n["status"] for n in dag["nodes"]}
    assert status["ingest"] == "success" and status["split"] == "failed"
    assert status["train"] == "never_run"


def test_runs_groups_terminal_runs(runner_app):
    client, *_ = runner_app
    runs = client.get("/api/v1/pipeline/runs").json()["runs"]
    assert len(runs) == 1  # three records within 90 s -> one CLI run
    assert runs[0]["status"] == "failed" and len(runs[0]["stages"]) == 3


def test_status_and_reports(runner_app):
    client, *_ = runner_app
    st = client.get("/api/v1/pipeline/status").json()
    assert st["state"] == "idle" and st["data_version"] == "v1"
    assert client.get("/api/v1/pipeline/reports").json()["metrics"]["test_micro_f1"] == 0.6


def test_trigger_requires_key_and_starts(runner_app):
    client, _, _, started = runner_app
    assert client.post("/api/v1/pipeline/trigger", json={}).status_code == 401
    r = client.post("/api/v1/pipeline/trigger", json={"data_version": "v2"},
                    headers={"X-API-Key": "test-key"})
    assert r.status_code == 202 and started[-1][2] == "v2"
    bad = client.post("/api/v1/pipeline/trigger", json={"data_version": "v7"},
                      headers={"X-API-Key": "test-key"})
    assert bad.status_code == 422


def test_alert_webhook(runner_app):
    client, _, _, started = runner_app
    hdr = {"Authorization": "Bearer test-key"}
    payload = {"alerts": [{"status": "firing", "labels": {"alertname": "PlotGenreHighLatency"}},
                          {"status": "firing", "labels": {"alertname": "PlotGenreDataDrift"},
                           "annotations": {"summary": "drift"}}]}
    actions = client.post("/api/v1/alerts", json=payload, headers=hdr).json()["actions"]
    assert [a["action"] for a in actions] == ["ignored", "retrain"]
    assert started[-1][0] == "drift_alert" and started[-1][2] == "v2"
    again = client.post("/api/v1/alerts", json=payload, headers=hdr).json()["actions"]
    assert again[1]["action"].startswith("skipped")


def test_set_data_version_preserves_comments(runner_app):
    _, rm, tmp, _ = runner_app
    rm.set_data_version("v2")
    text = (tmp / "params.yaml").read_text()
    assert "data_version: v2" in text and "# Data versions" in text
    assert rm.current_data_version() == "v2"


def test_log_endpoint_validation(runner_app):
    client, _, tmp, _ = runner_app
    assert client.get("/api/v1/pipeline/runs/nope/log").status_code == 404
    (tmp / "logs").mkdir()
    (tmp / "logs" / "abc.log").write_text("line1\nline2\n")
    assert client.get("/api/v1/pipeline/runs/abc/log").json()["lines"] == ["line1", "line2"]
