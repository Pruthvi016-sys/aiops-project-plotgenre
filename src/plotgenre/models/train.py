"""Stage 5 - train (with MLflow experiment tracking).

For each candidate model (One-vs-Rest LogisticRegression, calibrated
LinearSVM, calibrated ComplementNB):

* fit on the train split, tune one global decision threshold on validation,
* log a *nested* MLflow run with params, validation metrics (micro/macro F1,
  precision, recall, Hamming loss, per-genre F1), training time, model size
  and per-document inference latency.

The parent run additionally logs: git commit/branch/dirty flag, DVC data
hashes, data version, the pipeline run id, data-quality and feature reports,
params.yaml, global feature importance (top words per genre) and the best
model as an MLflow pyfunc whose only artifact is an **encrypted** pickle.
The best model is registered in the MLflow Model Registry; promotion to the
``champion`` alias happens in the evaluate stage.

Note on autolog: ``mlflow.sklearn.autolog`` is used in the featurize stage
(TF-IDF vectoriser). It is deliberately *not* enabled around the classifier
fits: its post-fit training-metric computation densifies the 50k-column
sparse matrix and runs out of memory. Everything listed above is therefore
explicit, custom logging.
"""

from __future__ import annotations

import json
import os
import pickle
import tempfile
import time
from pathlib import Path
from typing import Dict, Tuple

import mlflow
import numpy as np
import pandas as pd
import scipy.sparse as sp
from mlflow.models import infer_signature
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, hamming_loss, precision_score, recall_score
from sklearn.multiclass import OneVsRestClassifier
from sklearn.naive_bayes import ComplementNB
from sklearn.svm import LinearSVC

from plotgenre.common.config import load_params, mlflow_tracking_uri, project_path
from plotgenre.common.crypto import encrypt_object
from plotgenre.common.gitinfo import file_md5, git_info
from plotgenre.common.logging_utils import get_logger
from plotgenre.common.run_tracker import _RUN_ID, track_stage
from plotgenre.models.explain import extract_weights, global_top_terms
from plotgenre.models.pyfunc_model import GenreModel, PlotGenrePyfunc

log = get_logger(__name__)
FEATURES = project_path("data", "features")


def build_candidate(name: str, cfg: Dict, seed: int):
    """Factory for the three candidate One-vs-Rest classifiers."""
    if name == "logreg":
        base = LogisticRegression(C=cfg["C"], max_iter=cfg["max_iter"], solver="liblinear",
                                  random_state=seed)
    elif name == "linear_svm":
        base = CalibratedClassifierCV(LinearSVC(C=cfg["C"], random_state=seed),
                                      cv=cfg["calibration_cv"], method="sigmoid")
    elif name == "complement_nb":
        base = CalibratedClassifierCV(ComplementNB(alpha=cfg["alpha"]),
                                      cv=cfg["calibration_cv"], method="sigmoid")
    else:
        raise ValueError(f"unknown candidate model '{name}'")
    return OneVsRestClassifier(base, n_jobs=1)


def multilabel_metrics(y_true: np.ndarray, y_pred: np.ndarray, prefix: str) -> Dict[str, float]:
    """Standard multi-label metrics with a key prefix (e.g. ``val_``)."""
    return {
        f"{prefix}micro_f1": f1_score(y_true, y_pred, average="micro", zero_division=0),
        f"{prefix}macro_f1": f1_score(y_true, y_pred, average="macro", zero_division=0),
        f"{prefix}samples_f1": f1_score(y_true, y_pred, average="samples", zero_division=0),
        f"{prefix}micro_precision": precision_score(y_true, y_pred, average="micro",
                                                    zero_division=0),
        f"{prefix}micro_recall": recall_score(y_true, y_pred, average="micro", zero_division=0),
        f"{prefix}hamming_loss": hamming_loss(y_true, y_pred),
    }


def apply_threshold(proba: np.ndarray, threshold: float) -> np.ndarray:
    """Binarise probabilities; always keep the top genre so no row is empty."""
    pred = (proba >= threshold).astype(int)
    empty = pred.sum(axis=1) == 0
    pred[empty, proba[empty].argmax(axis=1)] = 1
    return pred


def tune_threshold(y_val: np.ndarray, proba: np.ndarray, grid) -> Tuple[float, float]:
    """Pick the global threshold maximising validation micro-F1."""
    scores = [(t, f1_score(y_val, apply_threshold(proba, t), average="micro",
                           zero_division=0)) for t in grid]
    return max(scores, key=lambda s: s[1])


def load_features():
    """Load sparse matrices, label matrices and label names produced by featurize."""
    X = {s: sp.load_npz(FEATURES / f"X_{s}.npz") for s in ("train", "val")}
    y = {s: np.load(FEATURES / f"y_{s}.npy") for s in ("train", "val")}
    labels = json.loads((FEATURES / "labels.json").read_text())
    with (FEATURES / "vectorizer.pkl").open("rb") as handle:
        vectorizer = pickle.load(handle)  # noqa: S301 - produced by our own pipeline
    return X, y, labels, vectorizer


def _log_json(obj, name: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / name
        path.write_text(json.dumps(obj, indent=2))
        mlflow.log_artifact(str(path), artifact_path="reports")


def main() -> None:  # noqa: C901 - linear orchestration, easier to read in one place
    """Entry point for the DVC ``train`` stage."""
    params = load_params()
    cfg = params["train"]
    mlflow.set_tracking_uri(mlflow_tracking_uri())
    mlflow.set_experiment(cfg["experiment_name"])

    with track_stage("train") as ctx:
        X, y, labels, vectorizer = load_features()
        provenance = git_info()
        tags = {**provenance, "pipeline_run_id": _RUN_ID,
                "data_version": params["split"]["data_version"], "stage": "train"}
        with mlflow.start_run(run_name=f"train-{params['split']['data_version']}",
                              tags=tags) as parent:
            mlflow.log_params({
                "data_version": params["split"]["data_version"],
                "cutoff_year": params["split"]["cutoff_year"],
                "n_train": X["train"].shape[0], "n_val": X["val"].shape[0],
                "n_features": X["train"].shape[1], "n_labels": len(labels),
                **{f"tfidf_{k}": v for k, v in params["featurize"].items()},
                "X_train_md5": file_md5(FEATURES / "X_train.npz"),
                "y_train_md5": file_md5(FEATURES / "y_train.npy"),
            })
            for report in ("data_quality.json", "split_summary.json",
                           "featurize_summary.json"):
                if project_path("reports", report).exists():
                    mlflow.log_artifact(str(project_path("reports", report)),
                                        artifact_path="reports")
            mlflow.log_artifact(str(project_path("params.yaml")), artifact_path="config")

            results = {}
            for name, model_cfg in cfg["candidates"].items():
                with mlflow.start_run(run_name=name, nested=True,
                                      tags={**tags, "candidate": name}):
                    clf = build_candidate(name, model_cfg, cfg["seed"])
                    t0 = time.time()
                    clf.fit(X["train"], y["train"])
                    train_s = time.time() - t0
                    t1 = time.time()
                    proba = clf.predict_proba(X["val"])
                    infer_ms = (time.time() - t1) * 1000 / X["val"].shape[0]
                    thr, _ = tune_threshold(y["val"], proba, cfg["threshold_grid"])
                    pred = apply_threshold(proba, thr)
                    metrics = multilabel_metrics(y["val"], pred, "val_")
                    per_genre = f1_score(y["val"], pred, average=None, zero_division=0)
                    size_kb = len(pickle.dumps(clf)) / 1024
                    mlflow.log_params({"model": name, "threshold": thr,
                                       **{f"hp_{k}": v for k, v in model_cfg.items()}})
                    mlflow.log_metrics({**metrics, "train_seconds": train_s,
                                        "val_inference_ms_per_doc": infer_ms,
                                        "model_size_kb": size_kb,
                                        **{f"val_f1_{g.replace(' ', '_')}": float(f)
                                           for g, f in zip(labels, per_genre)}})
                    results[name] = {"clf": clf, "threshold": thr, "metrics": metrics,
                                     "train_seconds": train_s}
                    log.info("%s: val micro-F1 %.4f (thr %.2f, %.1fs)", name,
                             metrics["val_micro_f1"], thr, train_s)

            best_name = max(results, key=lambda n: results[n]["metrics"]["val_micro_f1"])
            best = results[best_name]
            weights = extract_weights(best["clf"])
            model = GenreModel(vectorizer, best["clf"], labels, best["threshold"], weights,
                               name=best_name, explain_top_k=cfg["explain_top_k"])
            enc_path = encrypt_object(model, project_path("models", "model.pkl.enc"))

            mlflow.log_param("best_model", best_name)
            mlflow.log_param("best_threshold", best["threshold"])
            mlflow.log_metrics({f"best_{k}": v for k, v in best["metrics"].items()})
            _log_json(global_top_terms(weights, model.feature_names, labels),
                      "feature_importance_top_terms.json")
            _log_json({n: {**r["metrics"], "threshold": r["threshold"],
                           "train_seconds": r["train_seconds"]} for n, r in results.items()},
                      "candidate_comparison.json")

            example = pd.DataFrame({"text": ["A detective hunts a serial killer in the city."]})
            signature = infer_signature(example, _example_output(),
                                        params={"top_k": 3, "explain": True})
            info = mlflow.pyfunc.log_model(
                name="model", python_model=PlotGenrePyfunc(),
                artifacts={"encrypted_model": str(enc_path)},
                code_paths=[str(project_path("src", "plotgenre"))],
                signature=signature, input_example=None,
                pip_requirements=_serving_requirements())
            version = mlflow.register_model(info.model_uri, cfg["registered_model_name"],
                                            tags={"best_model": best_name,
                                                  "git_commit": provenance["git_commit"],
                                                  "data_version": tags["data_version"]})
            run_info = {
                "run_id": parent.info.run_id,
                "experiment_id": parent.info.experiment_id,
                "model_uri": info.model_uri,
                "registered_model_name": cfg["registered_model_name"],
                "model_version": str(version.version),
                "best_model": best_name,
                "threshold": best["threshold"],
                "data_version": tags["data_version"],
                "pipeline_run_id": _RUN_ID,
                **provenance,
            }
            project_path("models", "run_info.json").write_text(json.dumps(run_info, indent=2))
            train_metrics = {"best_model": best_name, "threshold": best["threshold"],
                             **{k: round(v, 4) for k, v in best["metrics"].items()},
                             "candidates": {n: round(r["metrics"]["val_micro_f1"], 4)
                                            for n, r in results.items()}}
            project_path("reports", "train_metrics.json").write_text(
                json.dumps(train_metrics, indent=2))
        ctx.set_rows(X["train"].shape[0])
        ctx.add(best_val_micro_f1=best["metrics"]["val_micro_f1"],
                registered_version=int(version.version))
        log.info("registered %s version %s (run %s)", cfg["registered_model_name"],
                 version.version, run_info["run_id"])


def _example_output() -> pd.DataFrame:  # noqa: N802 - mirrors class name
    """Example output used to infer the model signature."""
    return pd.DataFrame({"genres": ["[]"], "keywords": ["[]"], "threshold": [0.3],
                         "model_name": ["logreg"]})


def _serving_requirements():
    """Pinned requirements recorded with the model (used by the model server)."""
    req = project_path("services", "model_server", "requirements.txt")
    if req.exists():
        return [ln.strip() for ln in req.read_text().splitlines()
                if ln.strip() and not ln.startswith("#")]
    return None


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    main()
