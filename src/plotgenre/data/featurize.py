"""Stage 4 - featurize (TF-IDF, parallelised with Ray tasks).

1. Fit a TF-IDF vectoriser on the *training* split only (no leakage).
2. Put the fitted vectoriser in the Ray object store and transform the
   train/val/test texts in parallel chunks with ``@ray.remote`` tasks.
3. Binarise the multi-label targets.

The stage is tracked as its own MLflow run: ``mlflow.sklearn.autolog`` records
the vectoriser's parameters automatically, and we add custom metrics
(vocabulary size, fit time, Ray transform throughput) and the summary report.

Outputs (``data/features/``): ``vectorizer.pkl``, ``X_{split}.npz``,
``y_{split}.npy``, ``labels.json``; plus ``reports/featurize_summary.json``.
"""

from __future__ import annotations

import json
import pickle
import time
from typing import List

import mlflow
import numpy as np
import pandas as pd
import ray
import scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import MultiLabelBinarizer

from plotgenre.common.config import load_params, mlflow_tracking_uri, project_path, section
from plotgenre.common.gitinfo import git_info
from plotgenre.common.logging_utils import get_logger
from plotgenre.common.run_tracker import _RUN_ID, track_stage

log = get_logger(__name__)
SPLITS = ("train", "val", "test")


def build_vectorizer(cfg: dict) -> TfidfVectorizer:
    """Create the TF-IDF vectoriser from params."""
    return TfidfVectorizer(
        lowercase=True, strip_accents="unicode", stop_words="english",
        max_features=cfg["max_features"], ngram_range=(1, cfg["ngram_max"]),
        min_df=cfg["min_df"], max_df=cfg["max_df"], sublinear_tf=cfg["sublinear_tf"],
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z]+\b", dtype=np.float32)


@ray.remote
def _transform_chunk(vectorizer, texts: List[str]) -> sp.csr_matrix:
    """Ray task: transform one chunk of texts with the shared fitted vectoriser."""
    return vectorizer.transform(texts)


def parallel_transform(vectorizer: TfidfVectorizer, texts: List[str],
                       chunk_size: int = 2000) -> sp.csr_matrix:
    """Transform ``texts`` in parallel Ray tasks and stack the sparse results."""
    vec_ref = ray.put(vectorizer)
    futures = [_transform_chunk.remote(vec_ref, texts[i:i + chunk_size])
               for i in range(0, len(texts), chunk_size)]
    parts = ray.get(futures)
    return sp.vstack(parts).tocsr() if parts else sp.csr_matrix((0, len(vectorizer.vocabulary_)))


def main() -> None:
    """Entry point for the DVC ``featurize`` stage."""
    cfg = section("featurize")
    labels = sorted(section("preprocess")["genre_keywords"].keys())
    in_dir = project_path("data", "splits")
    out_dir = project_path("data", "features")
    out_dir.mkdir(parents=True, exist_ok=True)
    params = load_params()
    mlflow.set_tracking_uri(mlflow_tracking_uri())
    mlflow.set_experiment(params["train"]["experiment_name"])
    mlflow.sklearn.autolog(log_models=False, log_datasets=False, silent=True)
    tags = {**git_info(), "pipeline_run_id": _RUN_ID, "stage": "featurize",
            "data_version": params["split"]["data_version"]}
    with track_stage("featurize") as ctx, \
            mlflow.start_run(run_name="featurize-tfidf", tags=tags):
        frames = {s: pd.read_parquet(in_dir / f"{s}.parquet") for s in SPLITS}
        t0 = time.time()
        vectorizer = build_vectorizer(cfg).fit(frames["train"]["text"].tolist())  # autologged
        fit_s = time.time() - t0
        mlflow.sklearn.autolog(disable=True)
        if not ray.is_initialized():
            ray.init(include_dashboard=False, ignore_reinit_error=True, log_to_driver=False,
                     object_store_memory=400 * 1024 * 1024)
        mlb = MultiLabelBinarizer(classes=labels)
        t1 = time.time()
        total = 0
        for split, frame in frames.items():
            X = parallel_transform(vectorizer, frame["text"].tolist())
            y = mlb.fit_transform(frame["genres"].str.split("|")).astype(np.int8)
            sp.save_npz(out_dir / f"X_{split}.npz", X)
            np.save(out_dir / f"y_{split}.npy", y)
            total += X.shape[0]
        transform_s = max(time.time() - t1, 1e-9)
        with (out_dir / "vectorizer.pkl").open("wb") as handle:
            pickle.dump(vectorizer, handle)
        (out_dir / "labels.json").write_text(json.dumps(labels))
        summary = {
            "vocabulary_size": len(vectorizer.vocabulary_),
            "labels": labels,
            "rows": {s: len(f) for s, f in frames.items()},
            "fit_seconds": round(fit_s, 2),
            "transform_seconds": round(transform_s, 2),
            "transform_throughput_rows_per_s": round(total / transform_s, 1),
        }
        project_path("reports", "featurize_summary.json").write_text(json.dumps(summary, indent=2))
        mlflow.log_metrics({"vocabulary_size": summary["vocabulary_size"],
                            "fit_seconds": fit_s, "transform_seconds": transform_s,
                            "transform_throughput_rows_per_s":
                                summary["transform_throughput_rows_per_s"],
                            **{f"rows_{k}": v for k, v in summary["rows"].items()}})
        mlflow.log_artifact(str(project_path("reports", "featurize_summary.json")),
                            artifact_path="reports")
        ctx.set_rows(total)
        ctx.add(vocabulary_size=summary["vocabulary_size"],
                transform_throughput_rows_per_s=summary["transform_throughput_rows_per_s"])
        log.info("featurize summary: %s", summary)
    ray.shutdown()


if __name__ == "__main__":
    main()
