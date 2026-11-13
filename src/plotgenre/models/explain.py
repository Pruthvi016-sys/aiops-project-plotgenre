"""Word-level explainability for linear text classifiers.

All three candidate models are linear in the TF-IDF space, so the evidence a
word gives for a genre is simply ``tfidf(word) * weight(genre, word)``. We
extract one weight vector per genre from each supported model type:

* One-vs-Rest LogisticRegression          -> ``coef_``
* One-vs-Rest Calibrated(LinearSVC)       -> mean ``coef_`` of the calibrated folds
* One-vs-Rest Calibrated(ComplementNB)    -> ``feature_log_prob_[1] - [0]``

The weights are pre-computed once at training time and stored in the model,
so explanations cost one sparse dot product per request.
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import scipy.sparse as sp


class UnsupportedModelError(TypeError):
    """Raised when weights cannot be extracted from an estimator."""


def _binary_weights(est) -> np.ndarray:
    """Weight vector (n_features,) of one binary estimator."""
    if hasattr(est, "calibrated_classifiers_"):
        vecs = [_binary_weights(c.estimator) for c in est.calibrated_classifiers_]
        return np.mean(vecs, axis=0)
    if hasattr(est, "coef_"):
        return np.asarray(est.coef_).ravel()
    if hasattr(est, "feature_log_prob_"):
        flp = np.asarray(est.feature_log_prob_)
        if flp.shape[0] != 2:
            raise UnsupportedModelError("expected a binary naive Bayes estimator")
        return flp[1] - flp[0]
    raise UnsupportedModelError(f"cannot extract weights from {type(est).__name__}")


def extract_weights(ovr_clf) -> np.ndarray:
    """Return a dense ``(n_labels, n_features)`` float32 weight matrix."""
    if not hasattr(ovr_clf, "estimators_"):
        raise UnsupportedModelError("expected a fitted OneVsRestClassifier")
    return np.vstack([_binary_weights(e) for e in ovr_clf.estimators_]).astype(np.float32)


def explain_row(x_row: sp.csr_matrix, weights: np.ndarray, feature_names: np.ndarray,
                label_idx: List[int], labels: List[str], top_k: int = 8) -> List[Dict]:
    """Top contributing words for the given genres of a single document.

    Args:
        x_row: 1 x n_features TF-IDF row.
        weights: (n_labels, n_features) weight matrix from :func:`extract_weights`.
        feature_names: vocabulary terms, index-aligned with columns.
        label_idx: indices of the genres to explain (usually the predicted ones).
        labels: genre names.
        top_k: number of words per genre.

    Returns:
        List of ``{"word", "genre", "weight"}`` sorted by weight (desc).
    """
    x_row = sp.csr_matrix(x_row)
    cols, vals = x_row.indices, x_row.data
    out: List[Dict] = []
    if cols.size == 0:
        return out
    for k in label_idx:
        contrib = vals * weights[k, cols]
        order = np.argsort(-contrib)[:top_k]
        for j in order:
            if contrib[j] <= 0:
                break
            out.append({"word": str(feature_names[cols[j]]), "genre": labels[k],
                        "weight": round(float(contrib[j]), 4)})
    out.sort(key=lambda d: d["weight"], reverse=True)
    return out


def global_top_terms(weights: np.ndarray, feature_names: np.ndarray, labels: List[str],
                     top_k: int = 15) -> Dict[str, List[str]]:
    """Most indicative terms per genre (feature-importance artifact for MLflow)."""
    return {labels[k]: [str(feature_names[i]) for i in np.argsort(-weights[k])[:top_k]]
            for k in range(len(labels))}
