"""Explainability weight extraction and pipeline run tracking."""

import json

import numpy as np
import pytest
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.multiclass import OneVsRestClassifier
from sklearn.naive_bayes import ComplementNB
from sklearn.preprocessing import MultiLabelBinarizer
from sklearn.svm import LinearSVC

from plotgenre.models.explain import (UnsupportedModelError, explain_row, extract_weights,
                                      global_top_terms)

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def xy(corpus):
    vec = TfidfVectorizer().fit(corpus["text"])
    mlb = MultiLabelBinarizer()
    return vec, vec.transform(corpus["text"]), mlb.fit_transform(corpus["genres"].str.split("|")), mlb


@pytest.mark.parametrize("base", [CalibratedClassifierCV(LinearSVC(), cv=2),
                                  CalibratedClassifierCV(ComplementNB(), cv=2)])
def test_extract_weights_shapes(xy, base):
    vec, X, y, _ = xy
    clf = OneVsRestClassifier(base).fit(X, y)
    assert extract_weights(clf).shape == (y.shape[1], X.shape[1])


def test_extract_weights_rejects_unfitted():
    with pytest.raises(UnsupportedModelError):
        extract_weights(object())


def test_explain_row_returns_relevant_words(fitted_model):
    m = fitted_model
    x = m.vectorizer.transform(["the haunted ghost screams in the night with blood"])
    idx = m.labels.index("Horror")
    words = explain_row(x, m.weights, m.feature_names, [idx], m.labels, top_k=5)
    assert words and all(w["genre"] == "Horror" and w["weight"] > 0 for w in words)
    assert {"ghost", "haunted", "blood"} & {w["word"] for w in words}
    tops = global_top_terms(m.weights, m.feature_names, m.labels, 5)
    assert set(tops) == set(m.labels)


def test_track_stage_records_success_and_failure(tmp_path, monkeypatch):
    from plotgenre.common import run_tracker

    runs = tmp_path / "runs.jsonl"
    monkeypatch.setattr(run_tracker, "RUNS_FILE", runs)
    with run_tracker.track_stage("unit_ok") as ctx:
        ctx.set_rows(10)
        ctx.add(score=0.5)
    with pytest.raises(RuntimeError):
        with run_tracker.track_stage("unit_fail"):
            raise RuntimeError("boom")
    recs = [json.loads(line) for line in runs.read_text().splitlines()]
    assert [r["status"] for r in recs] == ["success", "failed"]
    assert recs[0]["rows"] == 10 and recs[0]["extra"]["score"] == 0.5
    assert "boom" in recs[1]["error"]


def test_genre_model_always_predicts_one_label(fitted_model):
    pred = fitted_model.predict_labels(["xyzzy plugh"])
    assert pred.sum() >= 1
    out = fitted_model.predict(["ghost haunted demon curse blood"], top_k=2)[0]
    assert out["genres"][0]["genre"] == "Horror"
    assert np.isclose(sum(1 for g in out["genres"]), len(fitted_model.labels))
