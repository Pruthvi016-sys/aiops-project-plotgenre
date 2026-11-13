#!/usr/bin/env bash
# Run the full DVC pipeline with one shared pipeline-run id (so the Pipeline
# console groups the stages), then push data/model versions to the DVC remote.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="src:${PYTHONPATH:-}"
export PIPELINE_RUN_ID="${PIPELINE_RUN_ID:-$(date -u +%Y%m%dT%H%M%S)-cli}"
export MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI:-http://localhost:5000}"
export PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-localhost:9091}"
echo "pipeline run ${PIPELINE_RUN_ID} -> MLflow ${MLFLOW_TRACKING_URI}"
dvc repro "$@"
dvc push || echo "warning: dvc push failed (is the remote folder reachable?)"
dvc metrics show reports/metrics.json
