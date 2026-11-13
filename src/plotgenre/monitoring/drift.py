"""Stage 7 - drift_check.

Compares the *training* distribution of the current data version with
*newer films* (release year >= cutoff_year), which stand in for the data the
deployed model will see in production.

* ``reports/drift_report.json`` - drift score (= JS distance to newer films
  divided by the JS distance to a same-size held-out training sample, i.e.
  "how many times larger than sampling noise"), threshold and the decision
  ``retrain_recommended``. Pushed to Prometheus; an alert rule on it fires the
  Alertmanager webhook of the pipeline-runner which retrains (data v2).
* ``reports/drift_reference.json`` - reference term profile + genre prior used
  by the gateway to compute *live* drift on incoming requests.
"""

from __future__ import annotations

import json
import statistics

import pandas as pd

from plotgenre.common.config import load_params, project_path
from plotgenre.common.logging_utils import get_logger
from plotgenre.common.run_tracker import track_stage
from plotgenre.monitoring.drift_core import build_reference, term_drift

log = get_logger(__name__)


def label_prior(genres: pd.Series) -> dict:
    """Share of training documents carrying each genre."""
    counts = genres.str.split("|").explode().value_counts()
    return {g: round(float(c) / len(genres), 5) for g, c in counts.items()}


def noise_floor(reference: dict, pool: pd.Series, n: int, draws: int, seed: int) -> float:
    """Mean JS distance between the reference and random same-size held-out samples."""
    values = [term_drift(reference, pool.sample(min(n, len(pool)), random_state=seed + i)
                         .tolist()) for i in range(draws)]
    return max(statistics.mean(values), 1e-6)


def main() -> None:
    """Entry point for the DVC ``drift_check`` stage."""
    params = load_params()
    cfg, cutoff = params["drift"], params["split"]["cutoff_year"]
    seed = params["split"]["seed"]
    with track_stage("drift_check") as ctx:
        train = pd.read_parquet(project_path("data", "splits", "train.parquet"))
        movies = pd.read_parquet(project_path("data", "processed", "movies.parquet"))
        newer = movies[movies["year"] >= cutoff]
        n = cfg["sample_size"]
        ref = train.sample(min(n, len(train)), random_state=seed)
        cur = newer.sample(min(n, len(newer)), random_state=seed)

        reference = build_reference(ref["text"].tolist(), cfg["top_terms"])
        raw = term_drift(reference, cur["text"].tolist())
        holdout = train.drop(ref.index)["text"]
        floor = noise_floor(reference, holdout, len(cur), cfg["floor_draws"], seed)
        online_floor = noise_floor(reference, holdout, cfg["online_window"],
                                   cfg["floor_draws"] * 4, seed)
        score = raw / floor

        report = {
            "data_version": params["split"]["data_version"],
            "reference_rows": len(ref), "current_rows": len(cur),
            "current_definition": f"films released in or after {cutoff}",
            "drift_score": round(score, 4),
            "js_distance": round(raw, 4),
            "noise_floor_js": round(floor, 4),
            "threshold": cfg["threshold"],
            "retrain_recommended": score > cfg["threshold"],
        }
        project_path("reports", "drift_report.json").write_text(json.dumps(report, indent=2))
        project_path("reports", "drift_reference.json").write_text(json.dumps({
            "terms": reference, "label_prior": label_prior(train["genres"]),
            "threshold": cfg["threshold"], "data_version": report["data_version"],
            "online_window": cfg["online_window"], "online_noise_floor_js": online_floor}))
        ctx.set_rows(len(ref) + len(cur))
        ctx.add(drift_score=report["drift_score"], drift_js_distance=report["js_distance"],
                drift_retrain_recommended=int(report["retrain_recommended"]))
        log.info("drift report: %s", report)


if __name__ == "__main__":
    main()
