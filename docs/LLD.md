# Low-level design (LLD)

This document covers the module layout, data schemas, the pipeline stages, the API endpoint specifications (inputs and outputs), the model contract, metrics and configuration. The live OpenAPI docs are at `http://localhost:8000/docs` (gateway) and `http://localhost:8100/docs` (pipeline runner).

## 1. Module layout

```
src/plotgenre/
  common/config.py        load_params(), section(), get_env() (.env fallback), project_path()
  common/logging_utils.py get_logger(): stdout + logs/pipeline.log
  common/crypto.py        encrypt_object(), decrypt_object(), generate_key()  (Fernet)
  common/gitinfo.py       git_info() commit/branch/dirty, file_md5()
  common/run_tracker.py   track_stage() context manager -> reports/pipeline_runs.jsonl + Pushgateway
  data/ingest.py          download(), safe_extract(), validate_raw()
  data/cleaning.py        clean_text(), parse_year(), parse_freebase_genres(), map_genres(), validate_record()
  data/preprocess.py      Ray Data pipeline: parse_plot_lines -> join_metadata -> clean_and_validate; quality_gate()
  data/split.py           select_version(), make_splits()
  data/featurize.py       build_vectorizer(), parallel_transform() (@ray.remote)
  models/train.py         build_candidate(), tune_threshold(), apply_threshold(), multilabel_metrics()
  models/evaluate.py      latency_profile(), champion_metric(), decide_promotion()
  models/explain.py       extract_weights(), explain_row(), global_top_terms()
  models/pyfunc_model.py  GenreModel, PlotGenrePyfunc (MLflow PythonModel)
  monitoring/drift_core.py tokenize(), build_reference(), js_distance(), term_drift(), label_drift()
  monitoring/drift.py     drift_check stage
services/
  gateway/app/            main.py (routes), schemas.py, clients.py, drift_monitor.py, metrics.py, config.py
  model_server/serve.py   Supervisor (deploy / redeploy / rollback) + metrics
  pipeline_runner/app/    main.py (Runner, console API, alert webhook)
  frontend/app/main.py    static UI, proxy, telemetry;  frontend/static/{index.html, styles.css, app.js}
```

## 2. Data schemas

**`data/processed/movies.parquet`** (output of preprocess; one row per film, sorted by `wiki_id`)

| column | type | description |
|---|---|---|
| wiki_id | str | Wikipedia id (primary key) |
| title | str | Film title |
| year | int64 | Release year (1900–2016) |
| text | str | Cleaned plot summary |
| n_words | int64 | Word count |
| genres | str | `|`-separated target genres, e.g. `Comedy|Romance` |

**`data/splits/{train,val,test}.parquet`** have the same schema. **`data/features/`** contains `X_{split}.npz` (CSR float32, n × 50,000), `y_{split}.npy` (int8, n × 12), `vectorizer.pkl` and `labels.json`.

**`reports/pipeline_runs.jsonl`** (one line per stage execution)
```json
{"pipeline_run_id": "20261107T080102-b67148", "stage": "preprocess", "status": "success",
 "started_at": "2026-11-07T08:01:05+00:00", "duration_s": 12.0, "rows": 42306,
 "throughput_rps": 3519.4, "error": null, "extra": {"rows_out": 34632, "ray_throughput_rows_per_s": 5080.7}}
```

## 3. Pipeline stages (dvc.yaml)

| Stage | Command | Deps | Params | Outputs | Metrics |
|---|---|---|---|---|---|
| ingest | `python -m plotgenre.data.ingest` | ingest.py | ingest | data/raw/MovieSummaries | – |
| preprocess | `…data.preprocess` | preprocess.py, cleaning.py, raw | preprocess | data/processed/movies.parquet | reports/data_quality.json |
| split | `…data.split` | split.py, movies.parquet | split | data/splits | reports/split_summary.json |
| featurize | `…data.featurize` | featurize.py, splits | featurize | data/features | reports/featurize_summary.json |
| train | `…models.train` | train.py, pyfunc_model.py, explain.py, features | train | models/model.pkl.enc, models/run_info.json | reports/train_metrics.json |
| evaluate | `…models.evaluate` | evaluate.py, model, run_info, features, splits | evaluate | – | reports/metrics.json, plot reports/per_genre_f1.csv |
| drift_check | `…monitoring.drift` | drift.py, movies.parquet, splits | drift, split.cutoff_year, split.seed | reports/drift_reference.json | reports/drift_report.json |

Every stage runs inside `track_stage(name)`, which records its status, duration, rows and throughput and pushes them to Prometheus. A failed quality gate raises an exception, so the stage and the run are marked *failed*.

## 4. Model contract (MLflow pyfunc, served at `model-server:5001`)

* **Artifact:** `encrypted_model` is a Fernet-encrypted pickle of `GenreModel` (vectoriser, OvR classifier, labels, threshold, explanation weights). `load_context` decrypts it with `PLOTGENRE_MODEL_KEY`.
* **Request:** `POST /invocations`
```json
{"dataframe_records": [{"text": "A detective hunts a killer..."}],
 "params": {"top_k": 3, "explain": true}}
```
* **Response:** one row per input. The columns are JSON strings, because the pyfunc output must be tabular.
```json
{"predictions": [{"genres": "[{\"genre\": \"Crime\", \"confidence\": 0.86, \"predicted\": true}, ...]",
                  "keywords": "[{\"word\": \"detective\", \"genre\": \"Crime\", \"weight\": 0.31}, ...]",
                  "threshold": 0.3, "model_name": "linear_svm"}]}
```
* **Signature:** input `text: string`. The params are `top_k: long = 3` and `explain: boolean = true`.
* **Explanation:** for each genre to explain, `contribution(word) = tfidf(word) × w_genre(word)`. `w` comes from `coef_` (LogReg), the mean of the calibrated folds' `coef_` (LinearSVM), or `feature_log_prob_[1] − [0]` (ComplementNB). The top `explain_top_k` positive contributions are returned.

## 5. Gateway API (`http://localhost:8000`)

The common error envelope, used for every non-2xx response:
```json
{"error": {"code": "text_too_short", "message": "Please write at least 5 words about the plot.", "request_id": "1d6db959d178"}}
```
Every response carries an `X-Request-ID` header. If the client sends an `X-Request-ID`, the gateway uses it.

| Method & path | Auth | Request | Success response | Errors |
|---|---|---|---|---|
| `GET /health` | – | – | `200 {"status":"ok","service":"gateway","version":"1.0.0","model_server":null}` | – |
| `GET /ready` | – | – | `200 {"status":"ready",…,"model_server":"up"}` | `503 {"status":"not_ready","model_server":"down"}` |
| `GET /metrics` | – | – | Prometheus text format | – |
| `GET /api/v1/genres` | – | – | `200 ["Action","Adventure",…,"Thriller"]` | – |
| `POST /api/v1/predict` | X-API-Key | `PredictRequest` | `200 PredictResponse` | 401 `unauthorized`; 422 `empty_text`, `text_too_short`, `text_too_long`, `invalid_input`; 502 `model_error`; 503 `model_unavailable`; 500 `internal_error` |
| `POST /api/v1/predict/batch` | X-API-Key | `BatchPredictRequest` | `200 BatchPredictResponse` | as above + 422 `batch_too_large` |
| `GET /api/v1/model` | X-API-Key | – | `200 ModelInfoResponse` | 401 |
| `GET /api/v1/monitoring/drift` | X-API-Key | – | `200 DriftResponse` | 401 |

**PredictRequest**

| field | type | constraints | default |
|---|---|---|---|
| text | string | required; after trimming: 5 ≤ words, ≤ 20,000 chars | – |
| top_k | int | 1–12 (number of predicted genres explained) | 3 |
| explain | bool | return keywords | true |

**PredictResponse**
```json
{
  "request_id": "e38e25d5144e",
  "predicted_genres": ["Crime", "Thriller", "Drama", "Action"],
  "genres": [{"genre": "Crime", "confidence": 0.9701, "predicted": true}, "... all 12, sorted desc"],
  "keywords": [{"word": "robbery", "genre": "Crime", "weight": 0.2875}],
  "model": {"name": "plotgenre-classifier", "version": "2", "algorithm": "linear_svm", "threshold": 0.3},
  "latency_ms": 84.2,
  "warnings": ["Short summary (12 words): predictions are more reliable with 30+ words."]
}
```
`predicted` means confidence ≥ threshold. If no genre reaches the threshold, the top genre is still marked as predicted.

**BatchPredictRequest:** `{"texts": [string, …] (1..50), "top_k": 3, "explain": false}`. **BatchPredictResponse:** `{"request_id", "count", "results": [PredictResponse…], "latency_ms"}`.

**ModelInfoResponse**
```json
{"name": "plotgenre-classifier", "alias": "champion", "version": "2", "run_id": "478b0c…",
 "algorithm": "linear_svm", "data_version": "v2", "git_commit": "d8b06f7…",
 "metrics": {"test_micro_f1": 0.668, "test_macro_f1": 0.621, "best_val_micro_f1": 0.664},
 "mlflow_run_url": "http://localhost:5000/#/experiments/1/runs/478b0c…"}
```

**DriftResponse**
```json
{"window_size": 300, "window_capacity": 300, "drift_score": 1.21, "label_drift": 0.09,
 "threshold": 2.0, "drift_detected": false, "reference_loaded": true, "reference_data_version": "v2"}
```

## 6. Pipeline-runner API (`http://localhost:8100`)

| Method & path | Auth | Request | Response |
|---|---|---|---|
| `GET /health` | – | – | `{"status":"ok","service":"pipeline-runner"}` |
| `GET /metrics` | – | – | Prometheus text |
| `GET /api/v1/pipeline/status?check_dvc=false` | – | – | `{"state":"idle|running","current_run":{…}|null,"last_run":{…},"data_version":"v1","stages":{"ingest":"success",…},"totals":{"runs":3,"success":3,"failed":0},"dvc":{"up_to_date":true,"changed_stages":[]}}` (`dvc` only when `check_dvc=true`) |
| `GET /api/v1/pipeline/runs?limit=20` | – | – | `{"count":n,"runs":[{"run_id","trigger":"manual|drift_alert|cli","reason","status":"running|success|failed","started_at","duration_s","data_version","exit_code","stages":[stage records]}]}` |
| `GET /api/v1/pipeline/runs/{run_id}/log?tail=200` | – | path `run_id` must match `[\w-]+` | `{"run_id","lines":[…]}`; 404 if no log |
| `GET /api/v1/pipeline/dag` | – | – | `{"nodes":[{"id","cmd","status","duration_s","rows","throughput_rps","last_run","params"}],"edges":[{"from","to"}]}` |
| `GET /api/v1/pipeline/reports` | – | – | `{"data_quality":{…},"split_summary":{…},"featurize_summary":{…},"train_metrics":{…},"metrics":{…},"drift_report":{…}}` |
| `POST /api/v1/pipeline/trigger` | X-API-Key | `{"reason": str ≤200, "data_version": "v1"|"v2"|null, "force": bool}` | `202 {run record}`; `409 already_running`; `401`; `422` |
| `POST /api/v1/alerts` | Bearer key | Alertmanager webhook payload `{"alerts":[{"status","labels":{"alertname"},"annotations"}]}` | `{"received":n,"actions":[{"alert","action":"retrain|ignored|skipped (running or cooldown)","run_id"?}]}` |

Retraining rule: an alert in `DRIFT_ALERT_NAMES` with status `firing`, while no run is active and outside `RETRAIN_COOLDOWN_S`, triggers `start("drift_alert", reason, data_version="v2")`.

## 7. Frontend server (`http://localhost:8080`)

| Method & path | Purpose | I/O |
|---|---|---|
| `GET /` , `GET /static/*` | Single-page UI | HTML/CSS/JS |
| `GET /config.js` | Runtime config (public URLs only) | `window.PLOTGENRE_CONFIG = {grafanaUrl, mlflowUrl, prometheusUrl, alertmanagerUrl, gatewayDocsUrl, grafanaDashboardUid, apiBase}` |
| `GET|POST /api/gateway/{path}` | Proxy to `GATEWAY_URL/{path}`, adds `X-API-Key` | allowed: `health`, `ready`, `api/v1/{predict, predict/batch, model, genres, monitoring/drift}`; other paths → 404 |
| `GET|POST /api/pipeline/{path}` | Proxy to `PIPELINE_URL/{path}` | allowed: `health`, `api/v1/pipeline/{status, runs, dag, reports, trigger, runs/<id>/log}` |
| `POST /telemetry` | Browser events | `{"type":"page_load|ui_error|action","page":str,"name":str?,"duration_ms":float?,"detail":str?}` → 204 |
| `GET /metrics`, `GET /health` | Ops | – |

If a backend is unreachable, the proxy returns `503 {"error":{"code":"backend_unreachable",…}}`.

## 8. Prometheus metrics

| Component | Metric | Type / labels |
|---|---|---|
| gateway | `plotgenre_gateway_requests_total` | counter {endpoint, method, status} |
| | `plotgenre_gateway_request_latency_seconds` | histogram {endpoint} |
| | `plotgenre_gateway_errors_total` | counter {endpoint, type} |
| | `plotgenre_gateway_requests_in_progress` | gauge |
| | `plotgenre_upstream_latency_seconds`, `plotgenre_upstream_errors_total{reason}`, `plotgenre_upstream_up` | model-server health as seen by the gateway |
| | `plotgenre_predicted_genre_total{genre}`, `plotgenre_prediction_top_confidence`, `plotgenre_input_words`, `plotgenre_predictions_total` | model output / input distribution |
| | `plotgenre_live_drift_score`, `plotgenre_live_label_drift`, `plotgenre_live_drift_window_size`, `plotgenre_drift_threshold` | live drift |
| frontend | `plotgenre_frontend_page_loads_total{page}`, `plotgenre_frontend_page_load_seconds{page}`, `plotgenre_frontend_ui_errors_total{page,kind}`, `plotgenre_frontend_actions_total{action}`, `plotgenre_frontend_proxy_requests_total{target,status}`, `plotgenre_frontend_proxy_latency_seconds{target}` | |
| model-server | `plotgenre_model_server_deployed_version`, `plotgenre_model_server_up`, `plotgenre_model_server_deployments_total`, `…_failed_deployments_total`, `…_rollbacks_total` | |
| pipeline-runner | `plotgenre_pipeline_runs_total{status,trigger}`, `plotgenre_pipeline_running`, `plotgenre_pipeline_last_duration_seconds`, `plotgenre_pipeline_last_success_timestamp`, `plotgenre_pipeline_last_run_success`, `plotgenre_pipeline_alerts_received_total{alertname,action}` | |
| DVC stages (Pushgateway) | `plotgenre_pipeline_stage_{duration_seconds, rows, throughput_rows_per_second, success, last_run_timestamp}{stage}` + extras: `plotgenre_pipeline_drift_score`, `…_test_micro_f1`, `…_latency_p95_ms`, `…_ray_throughput_rows_per_s`, `…_vocabulary_size`, … | |
| host | node-exporter `node_*` | |

Alert rules are defined in `monitoring/prometheus/alert_rules.yml`: `PlotGenreDataDrift`, `PlotGenreLiveInputDrift` (both carry `action=retrain`), `PlotGenreHighErrorRate`, `PlotGenreHighLatency`, `PlotGenreModelServerDown`, `PlotGenrePipelineFailed` and `PlotGenreUIErrors`.

## 9. Configuration

| Variable | Used by | Default / source |
|---|---|---|
| `API_KEY` / `API_KEYS` | gateway, runner, frontend, alertmanager (`.secrets/api_key`) | `.env` |
| `PLOTGENRE_MODEL_KEY` | train/evaluate stages, model-server | `.env` |
| `MLFLOW_TRACKING_URI` | stages, gateway, model-server | `http://mlflow:5000` |
| `MODEL_SERVER_URL`, `UPSTREAM_TIMEOUT_S`, `UPSTREAM_RETRIES`, `MIN_WORDS`, `WARN_WORDS`, `MAX_CHARS`, `MAX_BATCH`, `DRIFT_REFERENCE_PATH`, `CORS_ORIGINS` | gateway | see `services/gateway/app/config.py` |
| `GATEWAY_URL`, `PIPELINE_URL`, `*_PUBLIC_URL` | frontend | docker-compose.yml |
| `MODEL_NAME`, `MODEL_ALIAS`, `POLL_SECONDS`, `SERVE_WORKERS`, `STARTUP_TIMEOUT` | model-server | docker-compose.yml |
| `PUSHGATEWAY_URL`, `RETRAIN_COOLDOWN_S`, `RUNNER_DVC_PUSH`, `DRIFT_ALERT_NAMES` | runner / stages | docker-compose.yml |
| everything ML-related | stages | `params.yaml` (tracked by DVC) |
