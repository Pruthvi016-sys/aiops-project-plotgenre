"""Generate monitoring/grafana/dashboards/plotgenre.json (provisioned into Grafana).

Kept as code so the dashboard is reviewable and versioned. Panel ids are
stable because the web UI embeds some of them (see services/frontend/static/app.js).
Run: python scripts/build_grafana_dashboard.py
"""

import json
from pathlib import Path

DS = {"type": "prometheus", "uid": "prometheus"}


def target(expr, legend="", ref="A"):
    return {"datasource": DS, "expr": expr, "legendFormat": legend, "refId": ref}


def panel(pid, title, kind, exprs, x, y, w=8, h=8, unit=None, thresholds=None, extra=None):
    p = {"id": pid, "title": title, "type": kind, "datasource": DS,
         "gridPos": {"x": x, "y": y, "w": w, "h": h},
         "targets": [target(e, l, chr(65 + i)) for i, (e, l) in enumerate(exprs)],
         "fieldConfig": {"defaults": {}, "overrides": []}, "options": {}}
    d = p["fieldConfig"]["defaults"]
    if unit:
        d["unit"] = unit
    if thresholds:
        d["thresholds"] = {"mode": "absolute", "steps": thresholds}
    elif kind in ("stat", "bargauge"):
        # Neutral colour: these values are informative, not good/bad.
        d["thresholds"] = {"mode": "absolute", "steps": [{"color": "blue", "value": None}]}
    if kind == "timeseries":
        d["custom"] = {"lineWidth": 2, "fillOpacity": 10, "showPoints": "never"}
        p["options"] = {"legend": {"displayMode": "list", "placement": "bottom"},
                        "tooltip": {"mode": "multi"}}
    if kind == "bargauge":
        p["options"] = {"orientation": "horizontal", "displayMode": "gradient",
                        "reduceOptions": {"calcs": ["lastNotNull"]}}
    if kind == "stat":
        p["options"] = {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value",
                        "graphMode": "none"}
    if extra:
        p.update(extra)
    return p


GREEN, AMBER, RED = "green", "orange", "red"
panels = [
    {"id": 100, "type": "row", "title": "Inference API (gateway + model server)",
     "gridPos": {"x": 0, "y": 0, "w": 24, "h": 1}, "collapsed": False, "panels": []},
    panel(1, "Requests per second by endpoint", "timeseries",
          [('sum by (endpoint) (rate(plotgenre_gateway_requests_total[1m]))', "{{endpoint}}")],
          0, 1, unit="reqps"),
    panel(2, "Prediction latency", "timeseries",
          [('histogram_quantile(0.5, sum by (le) (rate(plotgenre_gateway_request_latency_seconds_bucket{endpoint="/api/v1/predict"}[5m])))', "p50"),
           ('histogram_quantile(0.95, sum by (le) (rate(plotgenre_gateway_request_latency_seconds_bucket{endpoint="/api/v1/predict"}[5m])))', "p95")],
          8, 1, unit="s", thresholds=[{"color": GREEN, "value": None}, {"color": RED, "value": 0.5}]),
    panel(3, "Error responses per second", "timeseries",
          [('sum by (status) (rate(plotgenre_gateway_requests_total{status=~"4..|5.."}[1m]))', "HTTP {{status}}"),
           ('sum(rate(plotgenre_upstream_errors_total[1m]))', "model-server errors")],
          16, 1, unit="reqps"),
    panel(4, "Predicted genres (count)", "bargauge",
          [('sum by (genre) (plotgenre_predicted_genre_total)', "{{genre}}")], 0, 9),
    panel(5, "Live input drift vs training data", "timeseries",
          [("plotgenre_live_drift_score", "drift score"), ("plotgenre_drift_threshold", "threshold"),
           ("plotgenre_live_label_drift", "genre-mix drift")], 8, 9,
          thresholds=[{"color": GREEN, "value": None}, {"color": RED, "value": 2.0}]),
    panel(6, "Model server latency (gateway -> MLflow serving)", "timeseries",
          [('histogram_quantile(0.95, sum by (le) (rate(plotgenre_upstream_latency_seconds_bucket[5m])))', "p95"),
           ('histogram_quantile(0.5, sum by (le) (rate(plotgenre_upstream_latency_seconds_bucket[5m])))', "p50")],
          16, 9, unit="s"),
    panel(10, "Model in service", "stat",
          [("plotgenre_model_server_deployed_version", "version"), ("plotgenre_model_server_up", "up"),
           ("sum(plotgenre_model_server_rollbacks_total)", "rollbacks")], 0, 17, w=8, h=5),
    panel(13, "Top-genre confidence (median)", "stat",
          [('histogram_quantile(0.5, sum by (le) (rate(plotgenre_prediction_top_confidence_bucket[15m])))', "median")],
          8, 17, w=4, h=5, unit="percentunit"),
    panel(14, "Words per plot (median)", "stat",
          [('histogram_quantile(0.5, sum by (le) (rate(plotgenre_input_words_bucket[15m])))', "words")],
          12, 17, w=4, h=5),
    panel(15, "Requests in progress", "stat",
          [("sum(plotgenre_gateway_requests_in_progress)", "in progress")], 16, 17, w=4, h=5),
    panel(16, "Predictions served", "stat",
          [("sum(plotgenre_predictions_total)", "total")], 20, 17, w=4, h=5),
    {"id": 101, "type": "row", "title": "ML pipeline (DVC stages, Ray, drift, retraining)",
     "gridPos": {"x": 0, "y": 22, "w": 24, "h": 1}, "collapsed": False, "panels": []},
    panel(7, "Stage throughput (rows / s, last run)", "bargauge",
          [("plotgenre_pipeline_stage_throughput_rows_per_second", "{{stage}}")], 0, 23,
          unit="rowsps"),
    panel(8, "Stage duration (s, last run)", "bargauge",
          [("plotgenre_pipeline_stage_duration_seconds", "{{stage}}")], 8, 23, unit="s"),
    panel(11, "Batch drift score (newer films)", "stat",
          [('max(plotgenre_pipeline_drift_score{stage="drift_check"})', "drift")], 16, 23, w=4,
          thresholds=[{"color": GREEN, "value": None}, {"color": RED, "value": 2.0}]),
    panel(12, "Pipeline runs", "stat",
          [('sum by (status) (plotgenre_pipeline_runs_total)', "{{status}}"),
           ("plotgenre_pipeline_running", "running now")], 20, 23, w=4),
    panel(17, "Stage result (1 = success)", "stat",
          [("plotgenre_pipeline_stage_success", "{{stage}}")], 0, 31, w=12, h=5,
          thresholds=[{"color": RED, "value": None}, {"color": GREEN, "value": 1}]),
    panel(18, "Model quality (last evaluation)", "stat",
          [('plotgenre_pipeline_test_micro_f1{stage="evaluate"}', "test micro-F1"),
           ('plotgenre_pipeline_latency_p95_ms{stage="evaluate"}', "p95 ms")], 12, 31, w=12, h=5),
    {"id": 102, "type": "row", "title": "Web UI and infrastructure",
     "gridPos": {"x": 0, "y": 36, "w": 24, "h": 1}, "collapsed": False, "panels": []},
    panel(9, "Web UI page loads and errors", "timeseries",
          [('sum by (page) (rate(plotgenre_frontend_page_loads_total[5m]))', "loads {{page}}"),
           ('sum by (kind) (rate(plotgenre_frontend_ui_errors_total[5m]))', "error {{kind}}")],
          0, 37, unit="reqps"),
    panel(19, "UI -> backend calls (p95 latency)", "timeseries",
          [('histogram_quantile(0.95, sum by (le, target) (rate(plotgenre_frontend_proxy_latency_seconds_bucket[5m])))', "{{target}}")],
          8, 37, unit="s"),
    panel(20, "Host CPU and memory", "timeseries",
          [('100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[1m])))', "CPU %"),
           ('100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)', "Memory %")],
          16, 37, unit="percent"),
]

dashboard = {
    "uid": "plotgenre-main", "title": "PlotGenre", "tags": ["plotgenre", "aiops"],
    "timezone": "browser", "schemaVersion": 39, "version": 1, "editable": True,
    "refresh": "10s", "time": {"from": "now-1h", "to": "now"}, "panels": panels,
    "annotations": {"list": []}, "templating": {"list": []},
}
out = Path(__file__).resolve().parents[1] / "monitoring/grafana/dashboards/plotgenre.json"
out.write_text(json.dumps(dashboard, indent=2))
print(f"wrote {out} with {len([p for p in panels if p['type'] != 'row'])} panels")
