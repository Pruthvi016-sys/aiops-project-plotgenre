# PlotGenre: an end-to-end AIOps pipeline for movie genre prediction

**DA3408 AI Operations project.** Mudda Manikanta Pruthvi Raj (DA24B016)

PlotGenre predicts the genres of a film from its plot summary. This is multi-label classification over 12 genres, trained on the CMU Movie Summary Corpus. A non-technical user pastes a plot and sees ranked genres, confidence scores and the words that influenced the prediction.

The point of the project is the **AIOps lifecycle** around the model: Ray data engineering, a DVC pipeline as CI, MLflow tracking and registry, MLflow serving behind a FastAPI gateway, Prometheus and Grafana monitoring, drift-triggered retraining, gated deployment with rollback, Docker Compose, tests and documentation. It all runs locally on Linux, with no cloud.

| | |
|---|---|
| Web UI | http://localhost:8080 |
| Gateway API (OpenAPI docs) | http://localhost:8000/docs |
| Pipeline runner API | http://localhost:8100/docs |
| MLflow | http://localhost:5000 |
| Grafana (dashboard "PlotGenre") | http://localhost:3000 (anonymous view; admin/admin to edit) |
| Prometheus / Alertmanager / Pushgateway | http://localhost:9090 / :9093 / :9091 |

Results from my run (Ubuntu 26.04, 12 cores, 14 GB RAM, 13–14 Nov 2026):

* **Test micro-F1 0.665** for the deployed model (v2, target ≥ 0.40)
* **p95 latency 18.7 ms** for the model alone and about 49 ms end to end through the gateway (target < 500 ms)
* **86/86 tests passed** (77 unit + integration, 9 end-to-end on the live stack)
* Ray preprocessing at 5,623 rows/s
* Batch drift 2.52 on newer films → alert → automatic retrain on data v2 → drift 1.65
* Full pipeline about 1 minute once the dataset is downloaded (the first download from the CMU server took 13 min on my network)

Evidence: every rubric item has a screenshot in [docs/screenshots/evidence/](docs/screenshots/evidence/), listed in [docs/evidence_checklist.md](docs/evidence_checklist.md).

---

## 1. Prerequisites (Ubuntu 22.04 / 24.04)

```bash
# Docker Engine + Compose v2 (https://docs.docker.com/engine/install/ubuntu/)
sudo apt update
sudo apt install -y git git-lfs openssl python3-venv
sudo usermod -aG docker $USER      # then log out and back in
docker compose version             # must print v2.x

# Python 3.12 is used for local development/tests (Ubuntu 24.04 ships it).
# On 22.04:  sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.12 python3.12-venv
# If the system Python is newer (e.g. 3.14 on 26.04), make a 3.12 interpreter with conda and pass it in:
#   conda create -y -n py312 python=3.12 && conda activate py312
#   PYTHON=python bash scripts/setup.sh && conda deactivate
```

Ports 3000, 5000, 5001, 8000, 8080, 8100, 9090, 9091 and 9093 must be free. Stop any Prometheus/Grafana left over from other projects first (`sudo ss -ltnp | grep -E ':(9090|9093|3000)'`).

The machine needs at least 4 CPU cores and 8 GB RAM to be comfortable, and about 6 GB of free disk for images and data.

## 2. First-time setup

```bash
unzip aiops-project-plotgenre.zip && cd aiops-project-plotgenre

# Secrets (.env, .secrets/), DVC remote folder, Git LFS, Python virtualenv
bash scripts/setup.sh                 # or: bash scripts/setup.sh --no-venv  (Docker only)
source .venv/bin/activate

# Git is required by DVC; commit before the first pipeline run
git init -b main
git lfs install
git add .
git commit -m "PlotGenre: initial commit"
```

## 3. Run everything with Docker Compose

```bash
docker compose up -d --build          # builds 4 images, starts 10 containers
docker compose ps                     # wait until mlflow/gateway/frontend are "healthy"
```

Then train the first model, using **either** of these options:

* **UI:** open http://localhost:8080 → **Pipeline** → **Run pipeline** → confirm.
* **CLI (inside the runner container):**
  ```bash
  curl -X POST localhost:8100/api/v1/pipeline/trigger \
       -H "X-API-Key: $(grep ^API_KEY= .env | cut -d= -f2)" \
       -H "Content-Type: application/json" -d '{"reason":"first run"}'
  ```

The first run downloads the dataset (48 MB) and takes 1–3 minutes. Then:

* The `evaluate` stage registers the model and gives it the `champion` alias.
* The model server picks it up within about 20 s, and the dot at the top right of the UI turns green.
* **Classify a plot** → click an example → **Find genres**.

Commit the pipeline results (DVC metadata + metrics) to Git:

```bash
git add dvc.lock reports/ params.yaml
git commit -m "pipeline run: data v1"
dvc push                               # data + encrypted model -> ../plotgenre-dvc-storage
```

## 4. Run the pipeline from the terminal (host)

With the Compose stack running (it provides MLflow and the Pushgateway):

```bash
source .venv/bin/activate
bash scripts/run_pipeline.sh          # = dvc repro + dvc push, with MLFLOW_TRACKING_URI=http://localhost:5000
dvc dag                               # the CI DAG
dvc metrics show                      # all stage metrics
dvc params diff                       # what changed vs last commit
dvc plots show reports/per_genre_f1.csv
mlflow run . -e pipeline --env-manager local   # same pipeline through the MLproject
```

Change a value in `params.yaml` (for example `featurize.max_features`), then run `dvc repro`. Only the affected stages re-run.

## 5. Demo script (evaluation)

1. **UI:** use the Classify page with the examples, look at the highlighted words, the mobile view (resize the window) and the Help page.
2. **Pipeline console:** look at the DAG with throughput, run history with logs, the reports and the embedded Grafana panels.
3. **Experiment tracking:** in MLflow (http://localhost:5000 → *Model training* → experiment `plotgenre`), see:
   * the parent run with git commit, data MD5, data version and pipeline run id
   * three nested candidate runs
   * the `featurize-tfidf` run (autolog)
   * artifacts: reports, feature importance, candidate comparison, `params.yaml`, the encrypted model
   * Models → `plotgenre-classifier` with the aliases `champion` and `previous`
4. **Drift → automatic retraining:**
   * The first run (data v1) produces `reports/drift_report.json` with `drift_score ≈ 2.4`, which is above 2.0.
   * Prometheus fires `PlotGenreDataDrift` (http://localhost:9090/alerts).
   * Alertmanager calls the runner webhook. A **Drift alert** run appears in the console, retrains on **data v2**, and the gated promotion deploys the new version.
   * The drift score then drops to about 1.7.
5. **Live input drift:**
   ```bash
   python scripts/simulate_traffic.py --mode normal --n 300   # drift ~1.2
   python scripts/simulate_traffic.py --mode ood --n 300      # out-of-domain text -> drift >> 2
   ```
   Watch Grafana's "Live input drift" panel and the `PlotGenreLiveInputDrift` alert.
6. **Rollback:**
   ```bash
   python scripts/rollback.py --list
   python scripts/rollback.py                 # champion -> previous; model server redeploys in ~20 s
   python scripts/rollback.py --version 2     # roll forward again
   ```
7. **Resilience:** run `docker compose stop model-server`. The UI shows a friendly retry message, and the `PlotGenreModelServerDown` alert fires. Bring it back with `docker compose start model-server`.

## 6. Tests and code quality

```bash
pytest -m "unit or integration"                      # 77 tests, ~10 s, no Docker needed
pip install playwright && playwright install --with-deps chromium   # once, for the browser e2e test
E2E_FRONTEND_URL=http://localhost:8080 E2E_GATEWAY_URL=http://localhost:8000 \
E2E_API_KEY=$(grep ^API_KEY= .env | cut -d= -f2) pytest -m e2e      # 9 tests on the live stack
python scripts/generate_test_report.py --e2e         # -> docs/test_report.md (counts + coverage)
flake8 src services scripts tests                    # PEP8
```

GitHub Actions (`.github/workflows/ci.yml`) runs lint, `dvc dag` validation and the unit and integration tests on every push.

## 7. Push to GitHub

```bash
git remote add origin https://github.com/Pruthvi016-sys/aiops-project-plotgenre.git
git push -u origin main
```

`.env`, `.secrets/`, data, models and MLflow state are git-ignored. Data and models are versioned by DVC (`dvc.lock` is in Git; the blobs live in the DVC remote). Screenshots, diagrams and the sample parquet are stored with **Git LFS** (`.gitattributes`).

## 8. Repository layout

```
params.yaml              all tunable parameters (DVC-tracked)
dvc.yaml / dvc.lock      7-stage pipeline (ingest → preprocess → split → featurize → train → evaluate, drift_check)
MLproject, python_env.yaml   MLflow Project (reproducible environment, entry points per stage)
docker-compose.yml       10 services
src/plotgenre/           ML package: data (Ray), models (MLflow), monitoring (drift), common (config, crypto, tracking)
services/gateway/        FastAPI gateway (inference API)
services/model_server/   MLflow serving + deployment supervisor
services/pipeline_runner/  pipeline console API (DVC orchestration, alert webhook)
services/frontend/       web UI + proxy + telemetry
monitoring/              Prometheus config + alert rules, Alertmanager, Grafana provisioning + dashboard
scripts/                 setup, run_pipeline, rollback, simulate_traffic, generate_test_report, build_grafana_dashboard
tests/                   unit / integration / e2e
docs/                    architecture, HLD, LLD, test plan + report, user manual, screenshots, diagrams
```

## 9. Documentation

| Document | File |
|---|---|
| Architecture diagram + block explanation | [docs/architecture.md](docs/architecture.md) |
| High-level design (choices and rationale) | [docs/HLD.md](docs/HLD.md) |
| Low-level design (endpoints, I/O, schemas, metrics) | [docs/LLD.md](docs/LLD.md) |
| Test plan, test cases, acceptance criteria | [docs/test_plan.md](docs/test_plan.md) |
| Test report | [docs/test_report.md](docs/test_report.md) |
| User manual (non-technical) | [docs/user_manual.md](docs/user_manual.md) |
| Rubric mapping | [docs/rubric_mapping.md](docs/rubric_mapping.md) |
| AI disclosure (course code of conduct) | [AI_DISCLOSURE.md](AI_DISCLOSURE.md) |

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| `PLOTGENRE_MODEL_KEY ... run scripts/setup.sh first` | Run `bash scripts/setup.sh --no-venv` |
| Runner log or `dvc`: `... is not a git repository` | `git init && git add . && git commit -m init` (section 2) |
| UI says "Model starting…" for minutes | No model registered yet. Run the pipeline once. Check `docker compose logs model-server`. |
| MLflow says "Invalid Host header" when opened by IP | `MLFLOW_ALLOWED_HOSTS="mlflow,mlflow:5000,localhost,localhost:5000,<ip>,<ip>:5000" docker compose up -d mlflow` |
| Ray "object store" or `/dev/shm` errors in the runner | Increase `shm_size` for `pipeline-runner` in docker-compose.yml |
| Files in the project owned by root | Make sure `.env` has your `UID`/`GID` (setup.sh writes them) |
| Reset everything | `docker compose down -v` (deletes MLflow/Prometheus/Grafana volumes) |

Dataset: D. Bamman, B. O'Connor, N. Smith, *Learning Latent Personas of Film Characters*, ACL 2013. CMU Movie Summary Corpus, CC BY-SA.
