# Rubric mapping and viva notes

This page maps every item of the *AI Application Evaluation Guideline* to where it is implemented, and adds short answers to likely viva questions.

## Demonstration (5)

| Rubric item | Where / how |
|---|---|
| Intuitive, non-technical UX | One task per screen: paste plot → **Find genres**. Four built-in examples. Plain-language labels. The plot comes back with explanations highlighted in genre colours. `services/frontend/static/` |
| Foolproof | The button stays disabled below 5 words, with a live word counter. A 20,000-character limit is enforced. Server-side validation returns friendly messages. Warnings appear for short or non-English text. A retry button shows on errors. A model-status dot sits in the header. Confirmation dialogs guard pipeline actions. |
| Free of UI errors | Playwright e2e test E2E-09 asserts no console errors. Telemetry counts UI errors (`plotgenre_frontend_ui_errors_total`) and alerts on them. |
| Colours / look and feel | A custom palette (archive paper, ink navy, film-leader amber) with 12 distinct genre colours. Archivo condensed headings and Atkinson Hyperlegible body text. Screenshots are in `docs/screenshots`. |
| Responsive | CSS grid with breakpoints at 980 and 640 px (`07_mobile_result.png`). Keyboard support (Ctrl+Enter, visible focus, skip link). Reduced motion is respected. |
| User manual | `docs/user_manual.md` and the in-app Help page |
| Separate pipeline visualisation screen | The **Pipeline** page shows: a DVC DAG rendered from `dvc.yaml` with per-stage status, duration and throughput; run history (manual, drift alert, terminal) with logs; reports; embedded Grafana panels; and links to MLflow, Prometheus and Alertmanager. |
| Pipeline management console | The *Run pipeline* and *Retrain with newer films* buttons start the runner; `POST /api/v1/pipeline/trigger` does the same. |
| Errors / failures / successful runs | The run history shows the status badge, per-stage ✓/✗ with the error text, and the console log. The success/failed totals are in the summary strip. The `PlotGenrePipelineFailed` alert fires on failure. |
| Speed and throughput | Each stage records rows and rows/s (shown in the DAG and in Grafana). In my run Ray preprocessing reached 5,623 rows/s and the TF-IDF transform about 5,000 rows/s. A full run takes about 1 min once the data is downloaded. |

## Software engineering (5)

| Rubric item | Where / how |
|---|---|
| Design document, architecture diagram, HLD | `docs/architecture.md`, `docs/HLD.md`, `docs/diagrams/*.png` |
| OO / functional | Functional pipeline stages (pure functions + thin `main`). Classes where there is state: `GenreModel`, `PlotGenrePyfunc`, `ModelServerClient`, `RegistryClient`, `DriftMonitor`, `Runner`, `Supervisor`. |
| LLD with endpoint I/O | `docs/LLD.md` §4–7, plus the live OpenAPI docs at `/docs` |
| Loose coupling over configurable REST | UI → proxy (`GATEWAY_URL`, `PIPELINE_URL`) → gateway → `MODEL_SERVER_URL`. Each block is a separate container. |
| PEP8 | `flake8` is clean (`.flake8`, max line length 100) and enforced in CI |
| Logging | Uniform format. Gateway access logs carry request ids. Pipeline logs go to `logs/pipeline.log` and per-run logs to `logs/runs/<id>.log`. |
| Exception handling | Custom exceptions (`IngestError`, `DataQualityError`, `ModelEncryptionError`, `UpstreamUnavailable`, `UpstreamError`, `APIError`). Global FastAPI handlers return one error envelope. Retries with backoff. Monitoring failures never break the pipeline. |
| Inline documentation | A module docstring explaining purpose and flow in every file, plus docstrings on all public functions and classes |
| Unit tests | 30 unit test functions (47 cases) in `tests/unit` |
| Test plan, cases, report, acceptance criteria | `docs/test_plan.md` (AC-1 to AC-5, UT/IT/E2E/MT cases) and `docs/test_report.md` (86 passed / 0 failed, all ACs met) |

## AIOps implementation (10)

| Rubric item | Where / how |
|---|---|
| Data ingestion / transformation pipeline with Ray | `data/preprocess.py` is a Ray Data DAG (`read_text → map_batches ×3`) with metadata held in the object store. `data/featurize.py` runs `@ray.remote` parallel TF-IDF transform. |
| Throughput and speed | `reports/data_quality.json` (`throughput_rows_per_s`), `reports/featurize_summary.json`, Pushgateway metrics, and the Grafana "Stage throughput" panel |
| CI with DVC; DVC DAG | `dvc.yaml` has 7 stages with deps, params, outs and metrics. Run `dvc dag`, `dvc repro`, `dvc push`. GitHub Actions validates the DAG and runs the tests. |
| Git, Git LFS, DVC versioning | Git for code and config. **Git LFS** for screenshots, diagrams and the sample parquet. **DVC** for raw, processed and feature data and the encrypted model (local remote `../plotgenre-dvc-storage`). Data versions v1/v2 come from `params.yaml`. |
| Experiment tracking: metrics, params, artifacts | **Params:** data version, cutoff, sizes, all TF-IDF and model hyper-parameters, threshold. **Metrics:** val/test micro/macro/samples F1, precision, recall, Hamming loss, per-genre F1, train time, inference ms/doc, model size, latency p50/p95, throughput. **Artifacts:** reports, `params.yaml`, feature-importance top terms, candidate comparison, per-genre CSV, the model. |
| Beyond autolog | `mlflow.sklearn.autolog` runs on the TF-IDF fit. On top of it, custom logging records the git commit/branch/dirty flag, data MD5 hashes, the pipeline run id, nested candidate runs, registry tags with the promotion decision, and test metrics appended by `evaluate`. |
| Prometheus instrumentation, all components | gateway, frontend, model-server, pipeline-runner, DVC stages (via Pushgateway) and the host (node-exporter): 6 scrape targets and more than 30 metric families (LLD §8) |
| Grafana in near real time | A provisioned 20-panel dashboard with 10 s refresh, 6 panels of which are embedded in the UI (`monitoring/grafana`) |
| MLflow APIfication | `mlflow models serve` of the registry alias `champion` (pyfunc with signature and params) |
| MLproject | `MLproject` + `python_env.yaml` with entry points for every stage, the full pipeline and the tests |
| FastAPI for the UI's APIs | `services/gateway` (inference) and `services/pipeline_runner` (console) |
| Dockerised frontend and backend as separate Compose services | `docker-compose.yml`: frontend, gateway, model-server, pipeline-runner, mlflow + monitoring (10 services) |

## Likely viva questions

**Why TF-IDF and linear models and not BERT?**
The brief emphasises AIOps rather than accuracy. Linear models train in seconds, serve in about 20 ms on a CPU, and give exact word-level explanations. Micro-F1 of 0.67 is well above the 0.40 target. A transformer could replace the model behind the same pyfunc contract without changing the gateway or the UI.

**Why One-vs-Rest, and why calibration?**
Multi-label means an independent yes/no per genre. LinearSVC and ComplementNB don't produce probabilities, so `CalibratedClassifierCV` (sigmoid) makes their confidences comparable and thresholdable.

**How is an experiment reproduced?**
Check out the git commit stored in the MLflow run (`git_commit` tag), then `dvc checkout` (the data hashes are in `dvc.lock` and also logged as `X_train_md5`), then `dvc repro`, or `mlflow run . -e train`. The params are in `params.yaml`, which is also logged as an artifact. Ray output is sorted, so splits are identical.

**How does the drift detection work?**
Drift is the Jensen-Shannon distance between the document-frequency distributions of the top 300 training terms, comparing training plots with current plots. It is divided by the distance you get between training plots and another same-size sample of training plots (the noise floor). A score near 1 means no drift. The threshold of 2.0 was calibrated: v1 vs newer films scores 2.4, v2 vs newer films 1.7, and out-of-domain text above 14.

**What happens when drift is detected?**
A Prometheus rule fires and Alertmanager routes it (`action=retrain`) to the runner webhook, authenticated with a Bearer key. The runner switches to data v2 and runs `dvc repro` and `dvc push`. `evaluate` promotes the new version only if it passes AC-1 and is at least as good as the champion. The supervisor then redeploys. A 30-minute cooldown prevents loops.

**How do rollbacks work?**
The registry aliases are `champion` and `previous`. `scripts/rollback.py` swaps them. The supervisor polls every 20 s and redeploys. If a new version fails its health check, the supervisor restarts the previous version itself (`plotgenre_model_server_rollbacks_total`).

**Why a gateway in front of MLflow serving?**
The gateway owns the product API contract, authentication, validation, friendly errors and business metrics (genre mix, live drift). The MLflow scoring server stays a replaceable internal component.

**How is loose coupling ensured?**
The UI only calls `/api/...` on its own server. The proxy forwards to URLs taken from environment variables. No code imports cross service boundaries, except the dependency-free `drift_core.py` copied into the gateway image.

**Security?**
* API keys, kept server-side, with Bearer auth for the webhook
* Fernet-encrypted model (tamper-evident)
* Secrets in a git-ignored `.env`
* Non-root containers
* MLflow allowed-hosts
* Proxy allow-list
* Safe tar extraction
* Input size limits

**Why Ray and not Spark?**
The data fits in memory, the team works in Python, and Ray needs no JVM and scales from a laptop to a cluster. Ray Data streams batches through the transformations, and Ray tasks parallelise featurisation.

**What would you do next?**
Per-genre thresholds, a transformer model behind the same contract, Kubernetes (KServe or Ray Serve) for autoscaling, a feedback endpoint to measure live accuracy, and Grafana alert annotations for deployments.
