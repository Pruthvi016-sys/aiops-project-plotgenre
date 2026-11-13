"""Stage 6 - evaluate + gated promotion (deployment with rollback safety).

1. Decrypt the freshly trained model and score the *held-out test split*
   end-to-end (raw text in -> genres out, exactly as in production).
2. Measure single-prediction latency (p50 / p95, explanation included).
3. Log test metrics to the same MLflow run as the training stage.
4. Promotion gate: the new registry version gets the ``champion`` alias only if
   it meets the acceptance criteria *and* is not worse than the current
   champion. The previous champion is kept under the ``previous`` alias, so a
   rollback is one alias switch (``scripts/rollback.py``). The model server
   watches the alias and redeploys automatically.

Outputs: ``reports/metrics.json`` (DVC metrics) and ``reports/per_genre_f1.csv``
(DVC plot).
"""

from __future__ import annotations

import json
import time
from typing import Dict, Optional

import mlflow
import numpy as np
import pandas as pd
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient
from sklearn.metrics import f1_score, precision_score, recall_score

from plotgenre.common.config import load_params, mlflow_tracking_uri, project_path
from plotgenre.common.crypto import decrypt_object
from plotgenre.common.logging_utils import get_logger
from plotgenre.common.run_tracker import track_stage
from plotgenre.models.train import multilabel_metrics

log = get_logger(__name__)


def latency_profile(model, texts, n: int = 200) -> Dict[str, float]:
    """p50/p95/mean latency (ms) of single-document predictions incl. explanation."""
    timings = []
    for text in texts[:n]:
        t0 = time.perf_counter()
        model.predict([text], top_k=3, explain=True)
        timings.append((time.perf_counter() - t0) * 1000)
    arr = np.asarray(timings)
    return {"latency_p50_ms": float(np.percentile(arr, 50)),
            "latency_p95_ms": float(np.percentile(arr, 95)),
            "latency_mean_ms": float(arr.mean())}


def champion_metric(client: MlflowClient, name: str, alias: str,
                    metric: str = "test_micro_f1") -> tuple[Optional[str], Optional[float]]:
    """Return (version, metric) of the current alias holder, or (None, None)."""
    try:
        mv = client.get_model_version_by_alias(name, alias)
    except MlflowException:
        return None, None
    run = client.get_run(mv.run_id)
    return mv.version, run.data.metrics.get(metric)


def decide_promotion(new_score: float, champ_score: Optional[float], min_score: float,
                     allow_equal: bool = True) -> tuple[bool, str]:
    """Pure promotion rule (unit tested)."""
    if new_score < min_score:
        return False, f"rejected: test micro-F1 {new_score:.4f} < acceptance {min_score:.2f}"
    if champ_score is None:
        return True, "promoted: no existing champion"
    better = new_score >= champ_score if allow_equal else new_score > champ_score
    if better:
        return True, f"promoted: {new_score:.4f} vs champion {champ_score:.4f}"
    return False, f"kept champion: {new_score:.4f} < champion {champ_score:.4f}"


def main() -> None:
    """Entry point for the DVC ``evaluate`` stage."""
    params = load_params()
    cfg = params["evaluate"]
    run_info = json.loads(project_path("models", "run_info.json").read_text())
    mlflow.set_tracking_uri(mlflow_tracking_uri())
    client = MlflowClient()
    name, alias = run_info["registered_model_name"], cfg["promote_alias"]

    with track_stage("evaluate") as ctx:
        model = decrypt_object(project_path("models", "model.pkl.enc"))
        test = pd.read_parquet(project_path("data", "splits", "test.parquet"))
        texts = test["text"].tolist()
        y_true = np.load(project_path("data", "features", "y_test.npy"))
        t0 = time.time()
        y_pred = model.predict_labels(texts)
        batch_s = max(time.time() - t0, 1e-9)
        metrics = {k: float(v) for k, v in multilabel_metrics(y_true, y_pred, "test_").items()}
        metrics.update(latency_profile(model, texts))
        metrics["test_batch_throughput_docs_per_s"] = len(texts) / batch_s
        per_genre = pd.DataFrame({
            "genre": model.labels,
            "f1": f1_score(y_true, y_pred, average=None, zero_division=0),
            "precision": precision_score(y_true, y_pred, average=None, zero_division=0),
            "recall": recall_score(y_true, y_pred, average=None, zero_division=0),
            "support": y_true.sum(axis=0),
        }).round(4)
        per_genre.to_csv(project_path("reports", "per_genre_f1.csv"), index=False)

        champ_version, champ_score = champion_metric(client, name, alias)
        promote, reason = decide_promotion(metrics["test_micro_f1"], champ_score,
                                           cfg["min_micro_f1"], cfg["allow_equal"])
        with mlflow.start_run(run_id=run_info["run_id"]):
            mlflow.log_metrics(metrics)
            mlflow.log_artifact(str(project_path("reports", "per_genre_f1.csv")),
                                artifact_path="reports")
            mlflow.set_tag("promotion_decision", reason)
        version = run_info["model_version"]
        if promote:
            if champ_version and champ_version != version:
                client.set_registered_model_alias(name, "previous", champ_version)
            client.set_registered_model_alias(name, alias, version)
        client.set_model_version_tag(name, version, "promotion_decision", reason)
        client.set_model_version_tag(name, version, "test_micro_f1",
                                     f"{metrics['test_micro_f1']:.4f}")
        log.info("%s (version %s)", reason, version)

        acceptance = {
            "micro_f1_ge_threshold": metrics["test_micro_f1"] >= cfg["min_micro_f1"],
            "p95_latency_lt_500ms": metrics["latency_p95_ms"] < 500,
        }
        report = {**{k: round(v, 4) for k, v in metrics.items()},
                  "model_version": version, "best_model": run_info["best_model"],
                  "promoted": promote, "promotion_reason": reason,
                  "previous_champion_version": champ_version,
                  "acceptance": acceptance, "acceptance_passed": all(acceptance.values())}
        project_path("reports", "metrics.json").write_text(json.dumps(report, indent=2))
        ctx.set_rows(len(texts))
        ctx.add(test_micro_f1=metrics["test_micro_f1"],
                latency_p95_ms=metrics["latency_p95_ms"], promoted=int(promote))


if __name__ == "__main__":
    main()
