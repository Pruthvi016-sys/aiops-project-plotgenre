# High-level design (HLD)

## 1. Problem and goals

Media libraries need genre labels for search and recommendations. Assigning them by hand is slow and inconsistent. PlotGenre predicts the genres of a film from its plot summary. This is a **multi-label text classification** task with 12 target genres.

The course asks for **engineering discipline across the ML lifecycle**, so maximum accuracy is not the main goal. The design therefore favours fast, transparent, linear models and puts the effort into automation, reproducibility, monitoring and operability.

| Goal | Measured by |
|---|---|
| Useful predictions | Test micro-F1 ≥ 0.40 (AC-1) |
| Interactive speed | p95 single-prediction latency < 500 ms (AC-2) |
| Correctness | All planned test cases pass (AC-3) |
| Reproducibility | Every model maps to a Git commit + MLflow run id + DVC data hash |
| Operability | One-command pipeline, live dashboards, automated retraining and rollback |

## 2. Data

* **CMU Movie Summary Corpus** (Bamman et al., 2013, CC BY-SA): 42,306 Wikipedia plot summaries and 81,741 metadata rows.
* The 300+ raw Freebase genres are mapped onto **12 target genres** by keyword rules in `params.yaml`. For example, "Romantic comedy" maps to Comedy and Romance. Keeping the rules in params makes the mapping version-controlled and tunable.
* **Cleaning rules:** remove markup, URLs and references. Reject plots with fewer than 30 or more than 3,000 words, a missing or out-of-range year, or no target genre. After cleaning, **34,632** usable plots remain.
* **Data versions by release year:** **v1** contains only films released before 2000 (20,863 plots). **v2** contains all films (34,632). The 13,769 newer films stand in for future production data, which lets us simulate realistic temporal drift.
* **Known biases:** Wikipedia plots skew towards US and European films. Drama and Comedy dominate (Drama is about 53%). Mystery and Fantasy are rare (about 6%). Macro-F1 is reported alongside micro-F1 for this reason.

## 3. Key design decisions and rationale

| Decision | Alternatives considered | Rationale |
|---|---|---|
| **Ray** for data engineering (Ray Data `map_batches` for preprocessing, `@ray.remote` tasks for parallel TF-IDF transform) | Spark, plain pandas | Ray is pure Python and needs no JVM. It scales from a laptop to a cluster with no code change, and it is the course's recommended tool. The data fits in memory, so Spark's overhead would not pay off. |
| **TF-IDF + linear One-vs-Rest models** (LogReg, calibrated LinearSVM, calibrated ComplementNB) | Transformers (BERT) | They train in seconds on a CPU and infer in milliseconds, and they are explainable *exactly* (contribution = tf-idf × weight). They reach micro-F1 of about 0.66, well above target. That leaves time for AIOps work, which the brief emphasises. |
| **One global decision threshold** tuned on validation | Per-class thresholds | Simple and robust. It always predicts at least one genre. |
| **DVC pipeline** (7 stages) as the CI DAG | Makefile, Airflow | `dvc repro` re-runs only changed stages, versions data and models next to Git, and `dvc.lock` makes runs reproducible. It is the course's CI tool. |
| **MLflow** tracking + Model Registry with **aliases** (`champion`, `previous`) | Stages (deprecated) | Aliases make promotion and rollback a single atomic metadata change. |
| **Gated promotion** in the `evaluate` stage | Always deploy latest | A new model goes live only if it meets the acceptance criteria and is at least as good as the champion. This prevents regressions. |
| **MLflow model serving + supervisor** watching the alias | Restarting containers via the Docker socket | The supervisor needs no privileged Docker access. Deployment and rollback happen automatically, and an unhealthy version is rolled back. |
| **FastAPI gateway** in front of MLflow serving | UI calling MLflow directly | The gateway owns a stable product API, authentication, validation and metrics. The model server stays replaceable. |
| **Frontend server with an allow-listed proxy** | Browser calling the gateway with CORS | Keeps the API key server-side and avoids CORS. Only the listed paths are reachable. |
| **Encrypted model artifact** (Fernet: AES-128-CBC + HMAC) | Plain pickle | Satisfies the security requirement. A tampered or foreign artifact fails HMAC verification before unpickling. |
| **Drift = term-distribution JS distance / sampling-noise floor** | Raw JS distance, KS tests on features | Normalising by the noise floor gives a sample-size-independent ratio (~1 = no drift). The threshold of 2.0 is calibrated: v1 vs newer films is 2.4, v2 vs newer films is 1.7, and out-of-domain traffic is above 14. |
| **Prometheus Pushgateway** for pipeline stages | Writing only to files | Batch jobs are short-lived, so they push their metrics. Grafana then shows pipeline throughput next to service metrics. |
| **Alertmanager webhook → runner** for retraining | Cron polling | Event-driven: the same alert that informs operators also starts the remediation. Includes a cooldown to prevent retrain loops. |

## 4. Paradigm

The code is **mostly functional**: pipeline stages are small pure functions (`cleaning.py`, `drift_core.py`, `split.py`) composed by a thin `main()`. **Object-oriented** design is used where there is state or a lifecycle:

* `GenreModel` and `PlotGenrePyfunc`: model and serving wrapper
* `ModelServerClient`, `RegistryClient`, `DriftMonitor`: gateway collaborators
* `Runner`: pipeline execution and history
* `Supervisor`: deployment loop

## 5. Non-functional design

* **Security:**
  * API keys on all mutating and inference endpoints (`X-API-Key` or Bearer).
  * The key lives server-side only, and secrets are kept in a git-ignored `.env`.
  * The model is encrypted at rest.
  * Containers run as non-root users.
  * MLflow `--allowed-hosts` protects against DNS rebinding.
  * The proxy uses an allow-list.
  * Tar extraction is protected against path traversal.
* **Reliability:**
  * Upstream retries with backoff, with 503 or 502 returned when the model is unavailable.
  * Health and readiness probes and Docker health checks.
  * Automatic rollback of a bad deployment.
  * Data-quality gates fail the pipeline early.
* **Observability:** structured logs with request ids, more than 30 Prometheus metrics across 6 scrape targets, 7 alert rules and a 20-panel Grafana dashboard.
* **Scalability:**
  * Ray parallelises preprocessing and featurisation across all cores, or across a cluster.
  * The stateless gateway and frontend can be replicated.
  * MLflow serving runs multiple workers (`SERVE_WORKERS`).
* **Reproducibility:** pinned dependencies, the MLproject `python_env.yaml`, identical Docker images, `dvc.lock`, and the git commit plus data MD5 logged to every MLflow run. Ray output is sorted, so the processed parquet is deterministic.
* **Usability:**
  * One task per screen, with examples and inline validation (the button stays disabled until there are 5 words).
  * Friendly error messages with a retry option.
  * Colour-coded explanations.
  * Responsive down to 360 px, with keyboard shortcuts and visible focus.
  * A user manual.

## 6. Results of my run (Ubuntu 26.04, 12 cores, 14 GB RAM)

| Item | Value |
|---|---|
| Ray preprocessing throughput | 5,623 rows/s (42,306 rows in 7.5 s) |
| Ray TF-IDF transform throughput | 4,968–5,277 rows/s |
| Full pipeline (7 stages) | 14 min first run (13 min was the dataset download), 69 s for the drift retrain, 42 s for a featurize-only change |
| Validation micro-F1 (v2): LogReg / LinearSVM / ComplementNB | 0.656 / **0.658** / 0.636 |
| Test micro-F1 / macro-F1 (champion, v2) | **0.665 / 0.618** (v1 was 0.658) |
| p95 latency: model only / end-to-end via gateway | **18.7 ms** / ~49 ms |
| Batch drift score: v1 vs newer films / after retrain on v2 | **2.52** (alert) / 1.65 (no alert) |
| Live input drift: normal traffic / out-of-domain traffic | 1.13 / **14.46** (alert) |
| Tests | 86/86 passed (77 unit + integration, 9 e2e) |
