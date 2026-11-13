"""Prometheus instrumentation of the gateway (exposed at ``GET /metrics``)."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, Info

LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)

REQUESTS = Counter("plotgenre_gateway_requests", "HTTP requests handled",
                   ["endpoint", "method", "status"])
LATENCY = Histogram("plotgenre_gateway_request_latency_seconds", "End-to-end request latency",
                    ["endpoint"], buckets=LATENCY_BUCKETS)
IN_PROGRESS = Gauge("plotgenre_gateway_requests_in_progress", "Requests being processed")
ERRORS = Counter("plotgenre_gateway_errors", "Errors by type", ["endpoint", "type"])

UPSTREAM_LATENCY = Histogram("plotgenre_upstream_latency_seconds",
                             "Latency of calls to the MLflow model server",
                             buckets=LATENCY_BUCKETS)
UPSTREAM_ERRORS = Counter("plotgenre_upstream_errors", "Failed calls to the model server",
                          ["reason"])
UPSTREAM_UP = Gauge("plotgenre_upstream_up", "1 if the model server answered the last ping")

PREDICTED_GENRE = Counter("plotgenre_predicted_genre", "Predicted genre counts", ["genre"])
TOP_CONFIDENCE = Histogram("plotgenre_prediction_top_confidence",
                           "Confidence of the top-ranked genre",
                           buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0))
INPUT_WORDS = Histogram("plotgenre_input_words", "Words per submitted plot",
                        buckets=(5, 10, 30, 60, 100, 200, 400, 800, 1600, 3200))
PREDICTIONS = Counter("plotgenre_predictions", "Documents classified")

LIVE_DRIFT = Gauge("plotgenre_live_drift_score",
                   "Live term drift (ratio to sampling-noise floor) over recent requests")
LIVE_LABEL_DRIFT = Gauge("plotgenre_live_label_drift",
                         "JS distance of predicted genre mix vs training prior")
DRIFT_WINDOW = Gauge("plotgenre_live_drift_window_size", "Requests in the drift window")
DRIFT_THRESHOLD = Gauge("plotgenre_drift_threshold", "Configured drift threshold")

MODEL_INFO = Info("plotgenre_gateway_model", "Champion model served behind the gateway")
BUILD_INFO = Info("plotgenre_gateway_build", "Gateway build information")
