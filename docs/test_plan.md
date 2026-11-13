# Test plan

## 1. Scope

The plan covers every software block: the data pipeline (ingest, Ray preprocessing, split, Ray featurisation), training helpers, evaluation and the promotion rule, explainability, encryption, drift statistics, pipeline run tracking, the gateway API, the pipeline-runner API, the frontend server and the deployed stack end to end, including the browser UI.

**Out of scope:** the internals of third-party tools (MLflow, DVC, Prometheus, Grafana), load testing beyond the p95 latency check, and model fairness.

## 2. Strategy

| Level | Marker | Tooling | Dependencies | Runs |
|---|---|---|---|---|
| Unit | `unit` | pytest | none (synthetic corpus fixture) | every commit (CI), `pytest -m unit` |
| Integration | `integration` | pytest, FastAPI `TestClient`, `httpx.MockTransport`, local Ray | none: upstream services are mocked, Ray runs in-process | every commit (CI) |
| End-to-end | `e2e` | pytest + httpx + Playwright (Chromium) | running `docker compose` stack | before a release / demo |
| Manual UI checks | – | browser, checklist below | running stack | before a release / demo |

* **Test data:** `tests/conftest.py` builds a deterministic synthetic corpus of 600 plots with 6 genres. Unit and integration tests therefore never need the 48 MB dataset and run in about 10 s.
* **Environment:** Ubuntu 22.04/24.04, Python 3.12 (CI) or the project virtualenv, with Docker Engine and Compose v2 for e2e.
* **Commands:**
  * `pytest -m "unit or integration"`
  * `pytest -m e2e` (with the `E2E_*` environment variables)
  * `python scripts/generate_test_report.py [--e2e]` writes `docs/test_report.md` with pass/fail counts and coverage.

## 3. Acceptance criteria

| ID | Criterion | How it is measured | Where |
|---|---|---|---|
| AC-1 | Test micro-F1 ≥ 0.40 on the held-out test split | `evaluate` stage, `reports/metrics.json` → `test_micro_f1` | E2E-08, promotion gate |
| AC-2 | p95 single-prediction latency < 500 ms | (a) model only, 200 single predictions incl. explanation (`latency_p95_ms`); (b) end-to-end through the gateway, 40 requests (E2E-04) | evaluate stage, E2E-04 |
| AC-3 | All planned automated test cases pass (0 failures) | `docs/test_report.md` | report |
| AC-4 | A model that fails AC-1, or is worse than the current champion, is never deployed | `decide_promotion` unit tests (UT-30) + `promotion_decision` tag in the registry | UT-30 |
| AC-5 | Drift above the threshold triggers retraining without manual action | IT-24, plus the demo: Prometheus alert → Alertmanager → runner run with `trigger=drift_alert` | IT-24, runbook |

The software is **accepted** when AC-1 to AC-5 hold. The reference run is in `docs/test_report.md`: AC-1 0.668, AC-2 23 ms model-only and 68 ms end-to-end p95, AC-3 86/86 passed.

## 4. Test cases

### Unit

| ID | Test (file::function) | What is verified | Expected |
|---|---|---|---|
| UT-01 | test_cleaning::test_clean_text_strips_markup_urls_refs_and_whitespace | HTML, URLs, `[12]` refs and `{{templates}}` removed; whitespace collapsed | exact clean string |
| UT-02 | test_cleaning::test_clean_text_empty (2 cases) | None / "" input | "" |
| UT-03 | test_cleaning::test_parse_year (6 cases) | `1999`, `1999-05-21`, `2010-03`, empty, None, `May 1999` | 4-digit year or None |
| UT-04 | test_cleaning::test_parse_freebase_genres_valid_and_invalid | JSON dict, invalid JSON, list, None | list of names / [] |
| UT-05 | test_cleaning::test_map_genres_multi_label_and_dedup | "Romantic comedy" → Comedy + Romance; unknown → [] | sorted unique labels |
| UT-06 | test_cleaning::test_word_count | token counting | 3 / 0 |
| UT-07 | test_cleaning::test_validate_record (7 cases) | every rejection reason + valid record | reason string / None |
| UT-08 | test_crypto::test_roundtrip | encrypt → decrypt; plaintext not visible on disk | equal object |
| UT-09 | test_crypto::test_wrong_key_is_rejected | decrypt with another key | `ModelEncryptionError` |
| UT-10 | test_crypto::test_tampered_file_is_rejected | flip one byte | `ModelEncryptionError` |
| UT-11 | test_crypto::test_missing_or_invalid_key | no key / malformed key | clear error message |
| UT-12 | test_drift_core::test_tokenize_lowercases_and_drops_stopwords_and_short_tokens | tokenizer | expected tokens |
| UT-13 | test_drift_core::test_js_distance_bounds | identical = 0, disjoint = 1, between in (0,1) | bounds hold |
| UT-14 | test_drift_core::test_js_distance_rejects_bad_input | unequal / empty vectors | `ValueError` |
| UT-15 | test_drift_core::test_term_drift_detects_shift | Horror reference vs other genres | shifted > 1.5 × same |
| UT-16 | test_drift_core::test_term_drift_empty_current_is_zero | empty window | 0.0 |
| UT-17 | test_drift_core::test_label_drift | same / skewed / empty predicted mix | 0, > 0.3, 0 |
| UT-18 | test_explain_and_tracker::test_extract_weights_shapes (2 cases) | calibrated LinearSVC and ComplementNB | (n_labels, n_features) |
| UT-19 | test_explain_and_tracker::test_extract_weights_rejects_unfitted | unsupported object | `UnsupportedModelError` |
| UT-20 | test_explain_and_tracker::test_explain_row_returns_relevant_words | horror text explains Horror with positive horror words; global top terms | ghost/haunted/blood present |
| UT-21 | test_explain_and_tracker::test_track_stage_records_success_and_failure | run log records success + failure with error text | 2 records |
| UT-22 | test_explain_and_tracker::test_genre_model_always_predicts_one_label | gibberish still gets ≥ 1 genre; horror text ranks Horror first | as stated |
| UT-23 | test_split_and_train_helpers::test_select_version | v1 = year < cutoff, v2 = all, invalid → error | as stated |
| UT-24 | test_split_and_train_helpers::test_make_splits_sizes_and_disjoint | 70/10/20 split, no overlap | disjoint, sizes |
| UT-25 | test_split_and_train_helpers::test_make_splits_is_reproducible | same seed → same split | identical ids |
| UT-26 | test_split_and_train_helpers::test_apply_threshold_never_returns_empty_rows | thresholding keeps top label | expected matrix |
| UT-27 | test_split_and_train_helpers::test_tune_threshold_picks_best | grid search | best thr 0.3, F1 1.0 |
| UT-28 | test_split_and_train_helpers::test_multilabel_metrics_perfect | perfect predictions | F1 1, Hamming 0 |
| UT-29 | test_split_and_train_helpers::test_build_candidate_unknown | unknown model name | `ValueError` |
| UT-30 | test_split_and_train_helpers::test_decide_promotion (5 cases) | below AC, no champion, worse, equal, better | reject / promote correctly |

### Integration

| ID | Test | What is verified | Expected |
|---|---|---|---|
| IT-01 | test_gateway_api::test_health_needs_no_auth | liveness without key | 200 ok |
| IT-02 | test_gateway_api::test_ready_reflects_model_server | readiness follows model server | 200 / 503 |
| IT-03 | test_gateway_api::test_predict_requires_api_key | no key | 401 `unauthorized` envelope |
| IT-04 | test_gateway_api::test_predict_success_contract | response matches LLD contract; request id header; model version from registry | 200 + fields |
| IT-05 | test_gateway_api::test_predict_validation (4 cases) | too short, blank, top_k=99, missing body | 422 with specific codes |
| IT-06 | test_gateway_api::test_short_text_warning | < 30 words | 200 + warning |
| IT-07 | test_gateway_api::test_model_server_down_gives_503 | connection refused, after retries | 503 `model_unavailable` |
| IT-08 | test_gateway_api::test_model_server_error_gives_502 | upstream 500 | 502 `model_error` |
| IT-09 | test_gateway_api::test_batch | batch of 2; batch of 51 | 200 count=2; 422 `batch_too_large` |
| IT-10 | test_gateway_api::test_model_info_and_genres | champion metadata, MLflow run URL, genre list | as stated |
| IT-11 | test_gateway_api::test_metrics_and_live_drift | drift window fills, all metric families exported | present |
| IT-12 | test_frontend::test_index_and_static | UI and assets served | 200 |
| IT-13 | test_frontend::test_config_exposes_no_secret | `/config.js` has no API key | secret absent |
| IT-14 | test_frontend::test_proxy_adds_key_and_respects_allow_list | key injected server-side; unknown / traversal paths blocked | 200 / 404 |
| IT-15 | test_frontend::test_backend_unreachable | backend down | 503 `backend_unreachable` |
| IT-16 | test_frontend::test_telemetry_metrics | page_load / ui_error recorded; bad event rejected | 204 / 422, metrics present |
| IT-17 | test_model_and_data::test_pyfunc_loads_encrypted_model_and_predicts | MLflow pyfunc decrypts and predicts; bad input column | correct genre; `ValueError` |
| IT-18 | test_model_and_data::test_ray_preprocess_pipeline | Ray Data pipeline on a synthetic raw corpus incl. a malformed line; quality gate | counts, reasons, throughput > 0 |
| IT-19 | test_model_and_data::test_ray_parallel_transform_matches_sequential | Ray-parallel TF-IDF = sequential | max diff < 1e-6 |
| IT-20 | test_model_and_data::test_quality_gate_rejects_bad_data | malformed share / missing genre | `DataQualityError` |
| IT-21 | test_pipeline_runner::test_dag_matches_dvc_yaml | DAG nodes/edges derived from dvc.yaml; stage status | expected edges |
| IT-22 | test_pipeline_runner::test_runs_groups_terminal_runs | CLI stage records grouped into one run | 1 run, failed |
| IT-23 | test_pipeline_runner::test_status_and_reports | status + reports endpoints | idle, v1, metrics |
| IT-24 | test_pipeline_runner::test_alert_webhook | drift alert → retrain on v2; other alert ignored; cooldown | actions as stated |
| IT-25 | test_pipeline_runner::test_trigger_requires_key_and_starts | auth, data_version validation | 401 / 202 / 422 |
| IT-26 | test_pipeline_runner::test_set_data_version_preserves_comments | params.yaml edit keeps comments | v2 + comments |
| IT-27 | test_pipeline_runner::test_log_endpoint_validation | run log tail, unknown run | lines / 404 |

### End-to-end (running stack)

| ID | Test | What is verified | Expected |
|---|---|---|---|
| E2E-01 | test_ui_is_served | UI reachable | 200 + title |
| E2E-02 | test_predict_through_ui_proxy | browser path: proxy → gateway → MLflow serving | Crime predicted, crime keywords |
| E2E-03 | test_gateway_enforces_api_key | direct gateway call without key | 401 |
| E2E-04 | test_p95_latency_under_500ms | 40 sequential requests | p95 < 500 ms (AC-2) |
| E2E-05 | test_model_info_matches_registry | champion registered, F1 ≥ 0.40 | ok |
| E2E-06 | test_pipeline_console_endpoints | status, 7-node DAG, runs via proxy | ok |
| E2E-07 | test_metrics_exposed | gateway + frontend metrics | present |
| E2E-08 | test_acceptance_criteria_report | `reports/metrics.json` AC-1, AC-2 | pass |
| E2E-09 | test_browser_flow | Chromium: button disabled until input; example → chips; Pipeline DAG renders; no console errors | ok |

### Manual UI checklist (MT)

| ID | Check | Expected | Result |
|---|---|---|---|
| MT-01 | Open http://localhost:8080 at 1366 px and 390 px width | Layout adapts, nothing overlaps, text readable | Pass (`docs/screenshots/02`, `07`) |
| MT-02 | Type 2 words | "Find genres" disabled, counter shows 2 words | Pass (`03`) |
| MT-03 | Stop the model server (`docker compose stop model-server`) and click Find genres | Friendly message + "Try again"; header shows a red dot and "Model starting…" | Pass (`08`) |
| MT-04 | Keyboard only: Tab to the textarea, Ctrl+Enter | Prediction runs, focus visible | Pass |
| MT-05 | Pipeline → "Run pipeline" → confirm | Toast with run id, state "Running…", run appears in history; Log button shows console output | Pass (`04`, `05`) |
| MT-06 | Grafana not running | Pipeline page shows instructions instead of empty frames | Pass |

## 5. Entry / exit criteria

* **Entry:** the code passes `flake8` and the stack builds (`docker compose build`).
* **Exit:** AC-1 to AC-5 satisfied, `docs/test_report.md` regenerated, and no open defects with severity "high".

## 6. Defects found during testing (and fixed)

| Defect | Found by | Fix |
|---|---|---|
| Ray returned pyarrow-backed dtypes; `.str` accessor failed in split | first pipeline run | normalise dtypes after Ray (`preprocess.py`) |
| Ray output order non-deterministic → split not byte-reproducible | comparing two runs | sort by `wiki_id` before writing parquet |
| `mlflow.sklearn.autolog` densified the sparse matrix → OOM | train stage | autolog only on the TF-IDF fit; explicit logging for classifiers |
| Model-server redeploy left old worker on the port | rollback test | process-group kill + wait until port is free |
| Drift threshold 1.5 kept firing after retraining (v2 = 1.7) | drift → retrain loop test | calibrated threshold 2.0 |
| Live drift on partial window over-estimated | traffic simulation | rescale noise floor by √(capacity/n) |
