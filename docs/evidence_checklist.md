# Evidence checklist (for TAs)

Every screenshot below was taken on my Ubuntu 26.04 laptop during a real run of this repository on 13–14 Nov 2026.

* Run evidence (terminal and tool UIs): `docs/screenshots/evidence/`
* Web UI screenshots used by the user manual: `docs/screenshots/`

## Demonstration (5)

| Rubric item | Screenshot | What it shows |
|---|---|---|
| Intuitive UI for a non-technical user | `screenshots/01_classify_empty.png`, `screenshots/02_classify_result.png` | Paste a plot, get ranked genres with confidence bars and the words that influenced them |
| Foolproof UX | `screenshots/03_classify_validation.png` | Button stays disabled under 5 words (the gateway also rejects it with a 422) |
| Free of UI errors / clear error states | `screenshots/08_error_model_down.png` | Model server stopped: friendly message, *Try again*, red status dot |
| Responsive UI | `screenshots/07_mobile_result.png` | iPhone 12 Pro layout (390 px) |
| User manual | `screenshots/06_help.png`, [user_manual.md](user_manual.md) | In-app help plus a separate manual |
| Separate pipeline screen + management console | `screenshots/04_pipeline_console.png`, `evidence/05_pipeline_console_drift_retrain.png` | DVC DAG with per-stage time and rows/s, Run / Retrain buttons, run history with Manual, Drift alert and Terminal runs |
| Errors / failures / successful runs | `screenshots/05_pipeline_run_log.png` | Console log of a run from the UI |
| Pipeline speed and throughput | `evidence/05_pipeline_console_drift_retrain.png`, `evidence/26_grafana_pipeline_ui_infra.png` | rows/s and seconds per stage (Ray preprocessing 5,623 rows/s) |

## Software engineering (5)

| Rubric item | Where |
|---|---|
| Architecture / HLD / LLD with endpoint I/O | [architecture](diagrams/architecture.png), [HLD.md](HLD.md), [LLD.md](LLD.md) |
| Loose coupling of UI and model (REST only) | `evidence/03_docker_compose_ps_images.png` (separate frontend, gateway and model-server containers), `evidence/20_gateway_swagger.png` |
| PEP8, unit tests | `evidence/29_flake8_unit_integration_tests.png` (flake8 clean, 77 passed) |
| API security | `evidence/21_gateway_api_key_200_401.png` (200 with key, 401 without) |
| Test plan, test cases, test report, acceptance criteria | [test_plan.md](test_plan.md), [test_report.md](test_report.md), `evidence/30_e2e_tests_live_stack.png`, `evidence/31_test_report_86_passed.png` (86/86 passed, criteria met) |

## AIOps implementation (10)

| Rubric item | Screenshot | What it shows |
|---|---|---|
| **Data engineering:** Ray pipeline, throughput | `evidence/08_dvc_partial_repro.png`, `evidence/06_dvc_metrics_show.png`, `evidence/15_mlflow_artifacts.png` | Ray stages with rows/s, data-quality report (42,306 in → 34,632 kept, reject reasons) |
| **CI with DVC:** DAG | `evidence/04_dvc_dag.png` | 7-stage DAG |
| **CI with DVC:** only changed stages rerun | `evidence/08_dvc_partial_repro.png`, `evidence/10_dvc_params_metrics_diff.png` | `max_features` change → ingest/preprocess/split/drift_check skipped; params and metrics diff |
| **Versioning:** Git, Git LFS, DVC remote | `evidence/02_git_push_lfs_ssh.png`, `evidence/07_dvc_push_remote_in_sync.png` | LFS files pushed over SSH; DVC cache and remote in sync |
| **Experiment tracking:** runs | `evidence/12_mlflow_runs_nested.png` | Parent runs with nested candidate models |
| **Experiment tracking:** params, metrics, tags beyond autolog | `evidence/13_mlflow_params.png`, `evidence/14_mlflow_metrics_tags_git_commit.png` | Data MD5s, data version, git commit, pipeline run id, promotion decision |
| **Experiment tracking:** artifacts, comparison | `evidence/15_mlflow_artifacts.png`, `evidence/16_mlflow_compare_plot.png`, `evidence/17_mlflow_compare_metrics.png` | Reports and config snapshot; 3 candidates compared |
| **Model registry, gated deployment** | `evidence/18_mlflow_registry_aliases.png`, `evidence/09_quality_gate_kept_champion.png` | champion / previous aliases; v3 rejected (0.6639 < 0.6651) |
| **Prometheus instrumentation, all components** | `evidence/23_prometheus_live_drift_firing.png`, `evidence/28_model_server_down_alert.png` | Alert rules over gateway, model server, pipeline, UI |
| **Grafana NRT** | `evidence/25_grafana_inference_api.png`, `evidence/26_grafana_pipeline_ui_infra.png` | API, drift, pipeline stages, UI and host panels with live data |
| **Drift → alert → retrain** | `evidence/22_live_drift_ood_traffic.png`, `evidence/23_prometheus_live_drift_firing.png`, `evidence/24_alertmanager_retrain_route.png`, `evidence/05_pipeline_console_drift_retrain.png` | Live drift 1.13 → 14.46; batch drift 2.52 triggered an automatic retrain on data v2 |
| **Rollback** | `evidence/27_rollback.png` | champion v2 → v1, served version changes without a restart |
| **MLflow APIfication** | `evidence/19_mlflow_model_server_curl.png` | MLflow scoring server `/invocations` |
| **MLproject** | `evidence/11_mlproject_tests_run.png` | `mlflow run . -e tests` |
| **FastAPI** | `evidence/20_gateway_swagger.png`, `evidence/21_gateway_api_key_200_401.png` | Gateway endpoints |
| **Docker, Compose, separate FE/BE services** | `evidence/01_setup_script.png`, `evidence/03_docker_compose_ps_images.png` | 10 containers, 4 built images |
| **CI on GitHub** | `evidence/32_github_actions_ci.png` | Lint + tests green on every push |
