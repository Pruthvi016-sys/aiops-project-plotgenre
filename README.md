# DA3408 Final Project: PlotGenre, an End-to-End AIOps Pipeline for Movie Genre Prediction

**Mudda Manikanta Pruthvi Raj, DA24B016**

PlotGenre predicts the genres of a film from its plot summary: multi-label classification over 12 genres, trained on the CMU Movie Summary Corpus. A user pastes a plot and sees the genres, a confidence score for each, and the words that led to the answer.

The project is about the AIOps lifecycle around the model:

* **Data engineering:** a Ray pipeline for ingest, cleaning and validation, and TF-IDF features, with measured throughput.
* **CI and versioning:** a 7-stage DVC pipeline as the CI DAG, with Git, Git LFS and DVC, and GitHub Actions.
* **Tracking and registry:** MLflow runs with custom params, metrics, tags and artifacts, and a registry with `champion` and `previous` aliases.
* **Serving:** MLflow model serving behind a FastAPI gateway, a separate web UI and pipeline console, and 10 Docker Compose services.
* **Operations:** Prometheus on every component, Grafana, and Alertmanager. Drift fires an alert, which retrains the model, which passes through a gated deployment, with one-command rollback.

| Video | Link |
|---|---|
| 🎥 Demo (under 10 min) | [Google Drive](https://drive.google.com/file/d/1bbEQ1cYrQdTlksP8qSSSbWW-IINPbJuq/view?usp=drivesdk) |

**Report:** [`PlotGenre_Project_Report_DA24B016.pdf`](PlotGenre_Project_Report_DA24B016.pdf) (11 pages). It covers the design, every AIOps part, the results, the tests and the problems found while running.

### Results from my run (Ubuntu 26.04, 12 CPUs, 14 GB RAM, 13–14 Nov 2026)

| Metric | Result | Target |
|---|---|---|
| Test micro-F1 / macro-F1 (deployed model v2) | **0.665** / 0.618 | micro-F1 ≥ 0.40 |
| p95 latency, model only / through the gateway | **18.7 ms** / ~49 ms | < 500 ms |
| Automated tests | **86 / 86 passed** (47 unit, 30 integration, 9 end-to-end) | all pass |
| Ray preprocessing throughput | **5,623 rows/s** (42,306 plots) | — |
| Batch drift on newer films → after automatic retrain | **2.52 → 1.65** | alert above 2.0 |
| Live input drift, normal → out-of-domain traffic | 1.13 → **14.46** | alert above 2.0 |
| Full pipeline after the first download / featurize-only change | 69 s / 42 s | — |

![Architecture](docs/diagrams/architecture.png)

---

## Where to find each requirement

The report is [`PlotGenre_Project_Report_DA24B016.pdf`](PlotGenre_Project_Report_DA24B016.pdf), and "§" means a report section. **UI-nn** means `docs/screenshots/nn_*.png`, and **Ennn** means `docs/screenshots/evidence/nn_*.png`. Both are listed at the [end](#evidence-screenshots).

### Demonstration: web UI and pipeline visualisation

| Requirement | Code | Report | Screenshot |
|---|---|---|---|
| Intuitive UI for a non-technical user: paste a plot or pick an example, genres with confidence bars, highlighted words | [`services/frontend/static/`](services/frontend/static) (`index.html`, `app.js`, `styles.css`) | §8.1 | UI-01, UI-02 |
| Foolproof UX: button disabled under 5 words, word counter, 422 from the API, friendly error with *Try again* | `app.js`; [`services/gateway/app/schemas.py`](services/gateway/app/schemas.py) | §8.1 | UI-03, UI-08 |
| No UI errors (clean browser console), look and feel, responsive (390 px phone layout) | `styles.css`, `app.js` (page-load telemetry fix) | §8.1, §13 | UI-02, UI-07 |
| User manual | [`docs/user_manual.md`](docs/user_manual.md), in-app Help page | §8.1 | UI-06 |
| Separate pipeline screen: DVC DAG with time and rows/s per stage, embedded Grafana, links to MLflow | Pipeline page in `app.js`; [`services/pipeline_runner/app/main.py`](services/pipeline_runner/app/main.py) (`/api/v1/pipeline/dag`, `/reports`) | §8.2 | UI-04, E05 |
| Management console: Run / Retrain buttons, run history with Manual, Drift-alert and Terminal triggers, successes, failures and logs | `pipeline_runner/app/main.py` (`trigger`, `/runs`, `/runs/{id}/log`) | §8.2 | UI-04, UI-05 |
| Pipeline speed and throughput | [`src/plotgenre/common/run_tracker.py`](src/plotgenre/common/run_tracker.py) | §4 (Table 5) | E05, E26 |

### Software engineering

| Requirement | Code / document | Report | Screenshot |
|---|---|---|---|
| Design document, HLD with reasons for each choice, HLD diagrams | [`docs/HLD.md`](docs/HLD.md), [`docs/architecture.md`](docs/architecture.md), [`docs/diagrams/`](docs/diagrams) | §3 | — |
| Architecture diagram | [`docs/diagrams/architecture.png`](docs/diagrams/architecture.png) | §3.1 (Fig. 1) | — |
| LLD: every endpoint with request and response I/O | [`docs/LLD.md`](docs/LLD.md); `schemas.py` (Pydantic) | §7.2 (Table 7) | E20 |
| Loose coupling: UI and model are separate containers joined only by configurable REST (`GATEWAY_URL`, `MODEL_SERVER_URL`) | [`services/frontend/app/main.py`](services/frontend/app/main.py) (proxy), [`services/gateway/app/clients.py`](services/gateway/app/clients.py) | §3.2 | E03, E21 |
| Paradigm: functional stages, plus classes where there is state (`GenreModel`, `PlotGenrePyfunc`, `ModelServerClient`, `DriftMonitor`, `Runner`, `Supervisor`) | [`src/plotgenre/`](src/plotgenre), [`services/`](services) | §3.4 | — |
| PEP8 (flake8 locally and in CI) | [`.flake8`](.flake8), [`.github/workflows/ci.yml`](.github/workflows/ci.yml) | §11 | E29 |
| Logging with request ids; exception handling (typed JSON errors, retries, 502/503/422, data-quality gate) | [`src/plotgenre/common/logging_utils.py`](src/plotgenre/common/logging_utils.py), `gateway/app/main.py`, `preprocess.py` → `quality_gate()` | §11 | — |
| Security: API key, encrypted model (Fernet + HMAC), non-root containers | `gateway/app/main.py`, [`src/plotgenre/common/crypto.py`](src/plotgenre/common/crypto.py) | §11 | E21 |
| Inline documentation | docstrings and comments throughout | §11 | — |
| Unit tests | [`tests/unit/`](tests/unit) (47) | §12 | E29 |
| Test plan, list of test cases, acceptance criteria | [`docs/test_plan.md`](docs/test_plan.md) | §2.1, §12 | — |
| Test report with counts, criteria met | [`docs/test_report.md`](docs/test_report.md) (86 passed, 0 failed) | §12 (Tables 9, 10) | E30, E31 |

### AIOps: data engineering

| Requirement | Code | Report | Screenshot |
|---|---|---|---|
| Ingestion pipeline (download with retries, skip if already present, check required files) | [`src/plotgenre/data/ingest.py`](src/plotgenre/data/ingest.py) | §4 | E05 |
| **Ray Data** transformation: `read_text` → `map_batches` (parse, join metadata, clean and validate) | [`src/plotgenre/data/preprocess.py`](src/plotgenre/data/preprocess.py), [`cleaning.py`](src/plotgenre/data/cleaning.py) | §4 | E15 |
| **Ray remote tasks** for the TF-IDF transform | [`src/plotgenre/data/featurize.py`](src/plotgenre/data/featurize.py) → `parallel_transform()` | §4 | E08 |
| Throughput and speed of every stage | `run_tracker.py`; reports in `reports/` | §4 (Table 5) | E05, E15, E26 |

### AIOps: source control and CI

| Requirement | Code | Report | Screenshot |
|---|---|---|---|
| DVC pipeline as CI: only changed stages re-run | [`dvc.yaml`](dvc.yaml), [`dvc.lock`](dvc.lock), [`params.yaml`](params.yaml) | §5 | E08, E10 |
| DVC DAG | `dvc dag` | §5 | E04 |
| Git (SSH to GitHub), Git LFS (screenshots, diagrams, sample data, PDFs), DVC remote for data and models | [`.gitattributes`](.gitattributes), [`.dvc/config`](.dvc/config) | §5 | E02, E07 |
| GitHub Actions on every push | [`.github/workflows/ci.yml`](.github/workflows/ci.yml) | §5 | E32 |

### AIOps: experiment tracking

| Requirement | Code | Report | Screenshot |
|---|---|---|---|
| Parent run with three nested candidate runs; featurize run | [`src/plotgenre/models/train.py`](src/plotgenre/models/train.py) | §6 | E12, E16, E17 |
| Beyond autolog: 15 params (data version, data MD5, TF-IDF settings, threshold), 16 metrics (F1s, precision, recall, latency, throughput), tags (`git_commit`, `pipeline_run_id`, `promotion_decision`) | `train.py`, [`evaluate.py`](src/plotgenre/models/evaluate.py), [`gitinfo.py`](src/plotgenre/common/gitinfo.py) | §6 | E13, E14 |
| Artifacts: params snapshot, data-quality, split and featurize reports, candidate comparison, top terms, per-genre F1, encrypted model | `train.py` | §6 | E15 |
| Model registry, gated promotion, `champion` and `previous` aliases | `evaluate.py` → `decide_promotion()` | §6, §10.3 | E09, E18 |

### AIOps: Prometheus and Grafana

| Requirement | Code | Report | Screenshot |
|---|---|---|---|
| Instrumentation of every component (gateway, frontend, model server, pipeline runner, DVC stages via Pushgateway, host) | [`services/gateway/app/metrics.py`](services/gateway/app/metrics.py), the `/metrics` route of each service, `run_tracker.py` | §9 (Table 8) | E23, E28 |
| Scrape targets and 7 alert rules | [`monitoring/prometheus/`](monitoring/prometheus) | §9 | UI-10, E23, E28 |
| Alertmanager routing `action=retrain` to the pipeline runner | [`monitoring/alertmanager/alertmanager.yml`](monitoring/alertmanager/alertmanager.yml); `/api/v1/alerts` | §9, §10 | E24 |
| Grafana in near real time (20 panels, 10 s refresh, provisioned as code) | [`monitoring/grafana/`](monitoring/grafana), [`scripts/build_grafana_dashboard.py`](scripts/build_grafana_dashboard.py) | §9 (Fig. 5) | UI-09, E25, E26 |
| Drift → alert → retrain → gate → deploy; live input drift | [`src/plotgenre/monitoring/drift_core.py`](src/plotgenre/monitoring/drift_core.py), [`services/gateway/app/drift_monitor.py`](services/gateway/app/drift_monitor.py) | §10.1, §10.2 | E05, E22–E24 |
| Rollback and resilience | [`scripts/rollback.py`](scripts/rollback.py), [`services/model_server/serve.py`](services/model_server/serve.py) → `Supervisor` | §10.3 | E27, E28, UI-08 |

### AIOps: software packaging

| Requirement | Code | Report | Screenshot |
|---|---|---|---|
| MLflow APIfication (`mlflow models serve`, pyfunc model) | `serve.py`, [`src/plotgenre/models/pyfunc_model.py`](src/plotgenre/models/pyfunc_model.py) | §7.1 | E19 |
| MLproject for identical dev and test environments | [`MLproject`](MLproject), [`python_env.yaml`](python_env.yaml) | §7.3 | E11 |
| FastAPI for every API the UI needs | [`services/gateway/app/main.py`](services/gateway/app/main.py), `pipeline_runner/app/main.py` | §7.2 | E20, E21 |
| Dockerised frontend and backend, kept as separate Compose services | `services/*/Dockerfile`, [`docker-compose.yml`](docker-compose.yml) | §7.3 | E01, E03 |

---

## Repository structure

```
.
├── README.md                          # this guide
├── PlotGenre_Project_Report_DA24B016.pdf   # the report (11 pages)
├── params.yaml                        # every tunable value (DVC-tracked)
├── dvc.yaml / dvc.lock                # 7-stage pipeline = the CI DAG; hashes of every output
├── MLproject, python_env.yaml         # MLflow Project: one entry point per stage + tests
├── docker-compose.yml                 # 10 services
├── .github/workflows/ci.yml           # lint, DVC DAG check, unit + integration tests
├── src/plotgenre/
│   ├── data/                          # ingest, preprocess (Ray Data), cleaning, split, featurize (Ray tasks)
│   ├── models/                        # train (3 candidates), evaluate (gate + registry), pyfunc model, explain
│   ├── monitoring/                    # drift score (batch and shared maths)
│   └── common/                        # config, logging, encryption, git info, run tracker (metrics)
├── services/
│   ├── frontend/                      # web UI (Classify, Pipeline, Help) + REST proxy + telemetry
│   ├── gateway/                       # FastAPI inference API: auth, validation, explanations, metrics, live drift
│   ├── model_server/                  # MLflow serving + supervisor (deploy champion, roll back on failure)
│   └── pipeline_runner/               # FastAPI console API: runs dvc repro, run history, Alertmanager webhook
├── monitoring/
│   ├── prometheus/                    # scrape config + 7 alert rules
│   ├── alertmanager/                  # routes action=retrain to the pipeline runner
│   └── grafana/                       # datasource + 20-panel dashboard (provisioned as code)
├── scripts/
│   ├── setup.sh                       # secrets, DVC remote, Git LFS, virtualenv
│   ├── run_pipeline.sh                # dvc repro + dvc push against the running stack
│   ├── rollback.py                    # list versions / roll champion back or forward
│   ├── simulate_traffic.py            # normal, newer-film or out-of-domain traffic
│   ├── generate_test_report.py        # writes docs/test_report.md from a real test run
│   └── build_grafana_dashboard.py
├── tests/
│   ├── unit/                          # 47 tests
│   ├── integration/                   # 30 tests
│   └── e2e/                           # 9 tests on the live stack (incl. a Playwright browser test)
├── data/sample/                       # small sample parquet (Git LFS); full data lives in DVC
└── docs/
    ├── architecture.md, HLD.md, LLD.md
    ├── test_plan.md, test_report.md, user_manual.md
    ├── evidence_checklist.md          # every rubric question → screenshot
    ├── diagrams/                      # architecture, request sequence, retrain loop, pipeline DAG
    └── screenshots/                   # UI-01..10, and evidence/ E01..E32
```

`.env`, `.secrets/`, `data/` (except the sample), `models/` and MLflow, Prometheus and Grafana state are not committed. Data and models are versioned by DVC: `dvc.lock` is in Git, and the files are in the DVC remote.

| Service | URL |
|---|---|
| Web UI | http://localhost:8080 |
| Gateway API docs | http://localhost:8000/docs |
| Pipeline runner API docs | http://localhost:8100/docs |
| MLflow | http://localhost:5000 (choose **Model training**) |
| Prometheus / Alertmanager / Pushgateway | http://localhost:9090 / :9093 / :9091 |
| Grafana (dashboard "PlotGenre") | http://localhost:3000 (anonymous view; admin/admin to edit) |

---

## How I ran it, end to end

Tested on an HP Laptop 15s (12 logical CPUs, 14 GiB RAM), Ubuntu 26.04, Docker 29.1, Compose 2.40. Run everything from the repository folder, after `source .venv/bin/activate` in every new terminal.

### 0. Prerequisites

```bash
sudo apt install -y git git-lfs openssl python3-venv
docker ps                                  # must work without sudo (else: sudo usermod -aG docker $USER, log out/in)
sudo ss -ltnp | grep -E ':(3000|5000|5001|8000|8080|8100|9090|9091|9093)\b'   # must print nothing
```

The project needs **Python 3.12**. Ubuntu 26.04 ships 3.14, so I made a 3.12 interpreter with conda just to create the virtualenv:

```bash
conda create -y -n py312 python=3.12 && conda activate py312
```

### 1. Setup and Git (E01, E02)

```bash
git clone git@github.com:Pruthvi016-sys/aiops-project-plotgenre.git
cd aiops-project-plotgenre
PYTHON=python bash scripts/setup.sh        # .env + secrets, ../plotgenre-dvc-storage, Git LFS, .venv
conda deactivate; conda deactivate
source .venv/bin/activate
```

### 2. Start the stack (E03)

```bash
docker compose up -d --build               # builds 4 images, starts 10 containers
docker compose ps                          # mlflow, gateway, frontend become (healthy)
docker images | grep plotgenre
```

### 3. First pipeline run, then drift and automatic retrain (UI-04, E05)

Open http://localhost:8080 → **Pipeline** → **Run pipeline**.

* The first run downloads the 48 MB dataset (13 min on my network) and trains on **data v1** (films before 2000).
* drift_check measured **2.52**. `PlotGenreDataDrift` fired, Alertmanager called the runner, and the runner retrained on **data v2** in 69 s.
* The gate promoted the new model (0.6651 vs 0.6581), and drift fell to **1.65**. I did nothing after the first click.

### 4. DVC: DAG, metrics, remote, partial re-run (E04, E06–E10)

```bash
dvc dag
dvc metrics show
dvc status -c && ls ../plotgenre-dvc-storage/files/md5 | head
git add -A && git commit -m "pipeline run: data v1 -> drift -> auto-retrain on v2" && git push

sed -i 's/^  max_features: 50000/  max_features: 40000/' params.yaml
dvc status                                 # only featurize changed
bash scripts/run_pipeline.sh               # skips ingest/preprocess/split/drift_check; gate kept v2 (0.6639 < 0.6651)
dvc params diff
dvc metrics diff --targets reports/metrics.json
```

### 5. MLflow (E12–E18)

Open http://localhost:5000 → **Model training** → **Runs**:

* the nested candidates
* parameters, metrics and tags (`git_commit`, `data_version`)
* artifacts
* Compare on the three candidates
* **Model registry** → `plotgenre-classifier`

### 6. Serving and API key (E19–E21)

```bash
curl -s -X POST localhost:5001/invocations -H 'Content-Type: application/json' \
  -d '{"dataframe_records":[{"text":"A retired hitman is pulled back into the criminal underworld when gangsters kill his dog, and he hunts them down one by one."}],"params":{"top_k":3,"explain":false}}' | python -m json.tool

API_KEY=$(grep ^API_KEY= .env | cut -d= -f2)
curl -s -o /tmp/resp.json -w "HTTP %{http_code}\n" -X POST localhost:8000/api/v1/predict \
  -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"text":"Two teenagers fall in love on a cruise ship that is doomed to sink in the cold Atlantic.","top_k":3,"explain":true}'
curl -s -w "\nHTTP %{http_code}\n" -X POST localhost:8000/api/v1/predict \
  -H 'Content-Type: application/json' -d '{"text":"Two teenagers fall in love on a cruise ship."}'
```

Then open http://localhost:8000/docs.

### 7. Live drift, alerts and Grafana (E22–E26)

```bash
python scripts/simulate_traffic.py --mode normal --n 300      # drift 1.13
python scripts/simulate_traffic.py --mode ood --n 300         # drift 14.46
```

After about 90 s:

* http://localhost:9090/alerts shows `PlotGenreLiveInputDrift` **FIRING**.
* http://localhost:9093 shows it routed to `pipeline-retrain`.
* http://localhost:3000 (Last 30 minutes) shows the spike.

Clear it with another `--mode normal` run.

### 8. Rollback and resilience (E27, E28, UI-08)

```bash
python scripts/rollback.py --list
python scripts/rollback.py                 # champion v2 -> v1; served within ~45 s, no restart
curl -s -H "X-API-Key: $API_KEY" localhost:8000/api/v1/model | head -c 200; echo
python scripts/rollback.py --version 2     # roll forward

docker compose stop model-server           # UI: friendly error; after 1 min PlotGenreModelServerDown fires
docker compose start model-server
```

### 9. Tests, MLproject and test report (E11, E29–E31)

```bash
flake8 src services scripts tests && echo "flake8: no PEP8 issues"
pytest -m "unit or integration" -q         # 77 passed
MLFLOW_TRACKING_URI=http://localhost:5000 mlflow run . -e tests --env-manager local

pip install playwright && playwright install chromium        # once, for the browser test
export E2E_FRONTEND_URL=http://localhost:8080 E2E_GATEWAY_URL=http://localhost:8000 E2E_API_KEY=$API_KEY
pytest -m e2e -v                           # 9 passed
python scripts/generate_test_report.py --e2e   # docs/test_report.md: 86 passed, 0 failed
```

### 10. Push and CI (E32)

```bash
git add -A && git commit -m "test report from local run" && git push
```

GitHub → **Actions** shows lint, the DVC DAG check and the tests passing on every push.

### Build the submission zip

```bash
rm -f ~/PlotGenre_DA24B016.zip
git ls-files | zip -q ~/PlotGenre_DA24B016.zip -@      # tracked files only: no .env, secrets, data or venv
```

### Troubleshooting

These are the problems I hit while running it, and their fixes.

| Symptom | Fix |
|---|---|
| `address already in use` on 9090, 9093 or 3000 | Old Prometheus/Grafana containers from another project: `docker stop prometheus alertmanager grafana node_exporter` |
| Prometheus "Up" but no port shown | `docker compose up -d --force-recreate prometheus alertmanager` |
| Alertmanager restarting (gossip mesh error) | Already fixed: it runs as a single node (`--cluster.listen-address=`) |
| `pip` fails on Python 3.13/3.14 | Create the venv from Python 3.12 (step 0) |
| Ingest stage slow | The CMU server is slow (about 65 KB/s for me). `ingest` skips the download if `data/raw/MovieSummaries.tar.gz` exists |
| UI says "Model starting…" | No model registered yet: run the pipeline once; check `docker compose logs model-server` |
| `dvc`: not a git repository | Commit once before the first run (`git add . && git commit -m init`) |
| `dvc metrics diff reports/metrics.json` error | Use `--targets reports/metrics.json` (DVC 3 reads plain arguments as revisions) |
| `mlflow run` created `mlflow.db` in the repo | Set `MLFLOW_TRACKING_URI=http://localhost:5000` (it is git-ignored anyway) |
| GitHub web upload refuses a PDF | PDFs are stored in Git LFS: add them with `git add` and `git push` from the terminal |
| Reset everything | `docker compose down -v` (deletes the MLflow, Prometheus and Grafana volumes) |

---

## Evidence screenshots

All from my run on 13–14 Nov 2026. [`docs/evidence_checklist.md`](docs/evidence_checklist.md) maps each rubric question to these.

**Web UI** ([`docs/screenshots/`](docs/screenshots))

| # | Shows |
|---|---|
| [UI-01](docs/screenshots/01_classify_empty.png) | Classify page, Model ready |
| [UI-02](docs/screenshots/02_classify_result.png) | Result: genres, confidence bars, influencing words, model v2 in 153 ms |
| [UI-03](docs/screenshots/03_classify_validation.png) | Under 5 words: button disabled |
| [UI-04](docs/screenshots/04_pipeline_console.png) | Pipeline console: DAG with stage speed; Manual, Drift-alert and Terminal runs |
| [UI-05](docs/screenshots/05_pipeline_run_log.png) | Console log of a run |
| [UI-06](docs/screenshots/06_help.png) | Help page |
| [UI-07](docs/screenshots/07_mobile_result.png) | Phone layout (iPhone 12 Pro), clean console |
| [UI-08](docs/screenshots/08_error_model_down.png) | Model server stopped: friendly error and Try again |
| [UI-09](docs/screenshots/09_grafana_dashboard.png) | Grafana dashboard |
| [UI-10](docs/screenshots/10_prometheus_alerts.png) | Prometheus alerts |

**Run evidence** ([`docs/screenshots/evidence/`](docs/screenshots/evidence))

| # | Shows |
|---|---|
| [E01](docs/screenshots/evidence/01_setup_script.png) | `setup.sh` complete, Compose v2 |
| [E02](docs/screenshots/evidence/02_git_push_lfs_ssh.png) | Push over SSH, 15 LFS files |
| [E03](docs/screenshots/evidence/03_docker_compose_ps_images.png) | 10 containers up, 4 images built |
| [E04](docs/screenshots/evidence/04_dvc_dag.png) | DVC DAG |
| [E05](docs/screenshots/evidence/05_pipeline_console_drift_retrain.png) | Drift 2.52 → automatic retrain on v2 → drift 1.65 |
| [E06](docs/screenshots/evidence/06_dvc_metrics_show.png) | `dvc metrics show` |
| [E07](docs/screenshots/evidence/07_dvc_push_remote_in_sync.png) | Cache and remote in sync; commits pushed |
| [E08](docs/screenshots/evidence/08_dvc_partial_repro.png) | Partial re-run: unchanged stages skipped, Ray started |
| [E09](docs/screenshots/evidence/09_quality_gate_kept_champion.png) | Gate: kept champion (0.6639 < 0.6651) |
| [E10](docs/screenshots/evidence/10_dvc_params_metrics_diff.png) | `dvc params diff`, `dvc metrics diff` |
| [E11](docs/screenshots/evidence/11_mlproject_tests_run.png) | `mlflow run . -e tests`: 77 passed |
| [E12](docs/screenshots/evidence/12_mlflow_runs_nested.png) | MLflow runs with nested candidates |
| [E13](docs/screenshots/evidence/13_mlflow_params.png) | 15 parameters incl. data MD5 |
| [E14](docs/screenshots/evidence/14_mlflow_metrics_tags_git_commit.png) | 16 metrics; tags incl. git commit |
| [E15](docs/screenshots/evidence/15_mlflow_artifacts.png) | Artifacts; data-quality report with Ray throughput |
| [E16](docs/screenshots/evidence/16_mlflow_compare_plot.png) | Candidate comparison plot |
| [E17](docs/screenshots/evidence/17_mlflow_compare_metrics.png) | Candidate metrics: linear SVM wins |
| [E18](docs/screenshots/evidence/18_mlflow_registry_aliases.png) | Registry: v2 @champion, v1 @previous, v3 rejected |
| [E19](docs/screenshots/evidence/19_mlflow_model_server_curl.png) | MLflow `/invocations` |
| [E20](docs/screenshots/evidence/20_gateway_swagger.png) | Gateway OpenAPI docs |
| [E21](docs/screenshots/evidence/21_gateway_api_key_200_401.png) | 200 with API key, 401 without |
| [E22](docs/screenshots/evidence/22_live_drift_ood_traffic.png) | Live drift 1.13 → 14.46 |
| [E23](docs/screenshots/evidence/23_prometheus_live_drift_firing.png) | `PlotGenreLiveInputDrift` firing |
| [E24](docs/screenshots/evidence/24_alertmanager_retrain_route.png) | Alertmanager routes to `pipeline-retrain` |
| [E25](docs/screenshots/evidence/25_grafana_inference_api.png) | Grafana: inference API and live drift |
| [E26](docs/screenshots/evidence/26_grafana_pipeline_ui_infra.png) | Grafana: pipeline stages, UI, host |
| [E27](docs/screenshots/evidence/27_rollback.png) | Rollback v2 → v1, served without restart |
| [E28](docs/screenshots/evidence/28_model_server_down_alert.png) | `PlotGenreModelServerDown` firing |
| [E29](docs/screenshots/evidence/29_flake8_unit_integration_tests.png) | flake8 clean, 77 tests passed |
| [E30](docs/screenshots/evidence/30_e2e_tests_live_stack.png) | 9 end-to-end tests passed |
| [E31](docs/screenshots/evidence/31_test_report_86_passed.png) | Test report: 86 passed, 0 failed |
| [E32](docs/screenshots/evidence/32_github_actions_ci.png) | GitHub Actions: all runs green |

Dataset: D. Bamman, B. O'Connor and N. A. Smith, *Learning Latent Personas of Film Characters*, ACL 2013 (CMU Movie Summary Corpus, CC BY-SA).

---

## AI Usage

* The problem, the dataset and the tool stack (Ray, DVC, MLflow, FastAPI, Prometheus/Grafana/Alertmanager, Docker Compose) come from my approved project statement.
* Claude generated most of the first version of the code, configuration files (Dockerfiles, `docker-compose.yml`, `dvc.yaml`, `MLproject`, Prometheus/Grafana/Alertmanager configs), tests and documentation, working from that statement and the course guideline documents.

After that, Claude was used mainly for correct syntax, exact command sequences, and debugging build, networking and monitoring issues as they came up. These included the port clashes, the Alertmanager restarts, the two false alerts, the UI telemetry bug and the MLproject quoting bug.

I ran every build, pipeline run, drift test, rollback and test suite myself on my laptop, took all the screenshots, and checked each result before it went into the report. Claude helped me draft the report and this README from those results, and I reviewed and edited them.

AI assistance had more impact on boilerplate, syntax reference and troubleshooting than on the design choices, which come from my project statement. Most of the hands-on work was done by hand: running the stack, triggering drift and rollback, and reading and verifying the evidence.
