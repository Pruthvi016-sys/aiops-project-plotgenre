"""Model objects.

``GenreModel``  - plain Python object: vectoriser + One-vs-Rest classifier +
                  tuned threshold + explanation weights. This is what gets
                  pickled and *encrypted*.
``PlotGenrePyfunc`` - the MLflow ``PythonModel`` wrapper. Its only artifact is
                  the encrypted file; ``load_context`` decrypts it with the key
                  from ``PLOTGENRE_MODEL_KEY``. MLflow model serving exposes it
                  at ``POST /invocations``.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

try:  # mlflow is optional for unit tests of GenreModel
    import mlflow.pyfunc

    _PythonModel = mlflow.pyfunc.PythonModel
except ImportError:  # pragma: no cover
    _PythonModel = object

from plotgenre.models.explain import explain_row


class GenreModel:
    """Multi-label genre classifier operating on raw text."""

    def __init__(self, vectorizer, classifier, labels: Sequence[str], threshold: float,
                 weights: np.ndarray, name: str, explain_top_k: int = 8) -> None:
        self.vectorizer = vectorizer
        self.classifier = classifier
        self.labels = list(labels)
        self.threshold = float(threshold)
        self.weights = weights
        self.name = name
        self.explain_top_k = explain_top_k
        self.feature_names = np.asarray(vectorizer.get_feature_names_out())

    def predict_proba(self, texts: Sequence[str]) -> np.ndarray:
        """Return (n_docs, n_labels) probabilities."""
        X = self.vectorizer.transform(list(texts))
        return np.asarray(self.classifier.predict_proba(X))

    def predict_labels(self, texts: Sequence[str]) -> np.ndarray:
        """Binary label matrix. At least one genre (the top one) is always predicted."""
        proba = self.predict_proba(texts)
        pred = (proba >= self.threshold).astype(int)
        empty = pred.sum(axis=1) == 0
        pred[empty, proba[empty].argmax(axis=1)] = 1
        return pred

    def predict(self, texts: Sequence[str], top_k: int = 3,
                explain: bool = True) -> List[Dict[str, Any]]:
        """Rich prediction per document: ranked genres, predicted set, keywords."""
        X = self.vectorizer.transform(list(texts))
        proba = np.asarray(self.classifier.predict_proba(X))
        results = []
        for i in range(X.shape[0]):
            order = np.argsort(-proba[i])
            ranked = [{"genre": self.labels[k], "confidence": round(float(proba[i, k]), 4),
                       "predicted": bool(proba[i, k] >= self.threshold)} for k in order]
            if not any(r["predicted"] for r in ranked):
                ranked[0]["predicted"] = True
            chosen = [k for k in order[:max(top_k, 1)]
                      if proba[i, k] >= self.threshold] or [int(order[0])]
            keywords = (explain_row(X[i], self.weights, self.feature_names, chosen,
                                    self.labels, self.explain_top_k) if explain else [])
            results.append({"genres": ranked, "keywords": keywords,
                            "threshold": self.threshold})
        return results


class PlotGenrePyfunc(_PythonModel):
    """MLflow pyfunc wrapper around an encrypted :class:`GenreModel`."""

    def load_context(self, context) -> None:  # noqa: D401 - MLflow hook
        """Decrypt and load the model artifact."""
        from plotgenre.common.crypto import decrypt_object

        self.model: GenreModel = decrypt_object(context.artifacts["encrypted_model"])

    def predict(self, context, model_input: pd.DataFrame,
                params: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
        """Input: DataFrame with a ``text`` column. Output: JSON-string columns."""
        params = params or {}
        if isinstance(model_input, pd.DataFrame):
            if "text" not in model_input.columns:
                raise ValueError("input must have a 'text' column")
            texts = model_input["text"].astype(str).tolist()
        else:
            texts = [str(t) for t in model_input]
        results = self.model.predict(texts, top_k=int(params.get("top_k", 3)),
                                     explain=bool(params.get("explain", True)))
        return pd.DataFrame({
            "genres": [json.dumps(r["genres"]) for r in results],
            "keywords": [json.dumps(r["keywords"]) for r in results],
            "threshold": [r["threshold"] for r in results],
            "model_name": [self.model.name] * len(results),
        })
