# Evidence checklist

Every screenshot is taken on my Ubuntu machine during a real run. Terminal shots show the command and its output. Browser shots show the URL bar. The system clock is visible in all of them.

* Terminal and service evidence goes in `docs/screenshots/evidence/` with the names below.
* UI screenshots keep their names in `docs/screenshots/` because the user manual uses them.

## Setup, Git, Docker (Software Packaging, Source Control)

| # | File | What it shows | Rubric |
|---|---|---|---|
| 1 | `E01_setup.png` | `bash scripts/setup.sh` output, `docker compose version` | Packaging |
| 2 | `E02_git_log_lfs.png` | `git log --oneline` and `git lfs ls-files` | Git, Git LFS |
| 3 | `E03_compose_build.png` | end of `docker compose up -d --build` | Docker |
| 4 | `E04_compose_ps.png` | `docker compose ps` with all 10 services up/healthy | Docker Compose, separate FE/BE services |
| 5 | `E05_docker_images.png` | `docker images \| grep plotgenre` | Docker |

## DVC pipeline (Data Engineering, CI)

| # | File | What it shows | Rubric |
|---|---|---|---|
| 6 | `E06_dvc_dag.png` | `dvc dag` | DVC DAG |
| 7 | `E07_dvc_repro.png` | `bash scripts/run_pipeline.sh`: Ray stage logs with rows/s | Ray pipeline, throughput |
| 8 | `E08_dvc_metrics.png` | `dvc metrics show` | CI, tracking |
| 9 | `E09_dvc_partial_repro.png` | `params.yaml` change → `dvc repro` re-runs only the affected stages, then `dvc params diff` | CI with DVC |
| 10 | `E10_dvc_push.png` | `dvc push`, `dvc status -c`, `ls ../plotgenre-dvc-storage` | DVC versioning |
| 11 | `E11_mlproject_run.png` | `mlflow run . -e tests --env-manager local` | MLproject |

## MLflow (Experiment Tracking, APIfication)

| # | File | What it shows | Rubric |
|---|---|---|---|
| 12 | `E12_mlflow_runs.png` | experiment `plotgenre`: parent and nested candidate runs | Tracking |
| 13 | `E13_mlflow_params_tags.png` | a run's parameters and tags (`git_commit`, data MD5, data version) | Beyond autolog |
| 14 | `E14_mlflow_metrics.png` | the same run's metrics | Metrics |
| 15 | `E15_mlflow_artifacts.png` | artifacts tab (reports, feature importance, encrypted model) | Artifacts |
| 16 | `E16_mlflow_compare.png` | the three candidates compared side by side | Model selection |
| 17 | `E17_mlflow_registry.png` | Models → `plotgenre-classifier` with `champion` / `previous` aliases | Registry, rollback |
| 18 | `E18_model_server_curl.png` | `curl` to the MLflow scoring server `localhost:5001/invocations` | MLflow serving |

## FastAPI gateway (Packaging, LLD)

| # | File | What it shows | Rubric |
|---|---|---|---|
| 19 | `E19_gateway_swagger.png` | http://localhost:8000/docs | FastAPI, LLD endpoints |
| 20 | `E20_gateway_curl.png` | `curl` predict with the API key (200), then without it (401) | Security, API |

## Web UI (Demonstration)

These keep the existing names in `docs/screenshots/` (replace the old files).

* `01_classify_empty.png`
* `02_classify_result.png`
* `03_classify_validation.png`
* `04_pipeline_console.png` (scroll so the Grafana panels have loaded)
* `05_pipeline_run_log.png`
* `06_help.png`
* `07_mobile_result.png` (browser dev tools, 390 px width)
* `08_error_model_down.png`

## Monitoring (Exporter Instrumentation and Visualization)

| # | File | What it shows | Rubric |
|---|---|---|---|
| 21 | `E21_prometheus_targets.png` | http://localhost:9090/targets with every target UP | All components monitored |
| 22 | `E22_prometheus_query.png` | a PromQL graph, e.g. `rate(plotgenre_gateway_requests_total[1m])` | Instrumentation |
| 23 | `E23_prometheus_alerts.png` | Alerts page with the drift alert firing (also save as `10_prometheus_alerts.png`) | Alerting |
| 24 | `E24_alertmanager.png` | http://localhost:9093 with the alert routed | Alerting |
| 25 | `E25_grafana_dashboard.png` | full Grafana dashboard with live data (also save as `09_grafana_dashboard.png`) | Grafana NRT |

## AIOps loop: drift, retraining, rollback, resilience

| # | File | What it shows | Rubric |
|---|---|---|---|
| 26 | `E26_drift_retrain_console.png` | Pipeline console with a "Drift alert" run that retrained on data v2 | Automated retraining |
| 27 | `E27_live_drift_ood.png` | `simulate_traffic.py --mode ood` + the Grafana live-drift panel spiking | Drift monitoring |
| 28 | `E28_rollback.png` | `python scripts/rollback.py --list` then a rollback; the registry aliases swapped | Rollback |
| 29 | `E29_model_down_alert.png` | `docker compose stop model-server` → `PlotGenreModelServerDown` firing | Resilience |

## Tests and code quality (Implementation, Testing)

| # | File | What it shows | Rubric |
|---|---|---|---|
| 30 | `E30_pytest_unit_integration.png` | `pytest -m "unit or integration"` summary | Unit tests |
| 31 | `E31_pytest_e2e.png` | `pytest -m e2e` on the live stack | E2E tests |
| 32 | `E32_flake8.png` | `flake8 src services scripts tests` with no output | PEP8 |
| 33 | `E33_test_report.png` | `python scripts/generate_test_report.py --e2e` summary | Test report, acceptance criteria |
| 34 | `E34_github_actions.png` | GitHub Actions run green (after pushing) | CI |
