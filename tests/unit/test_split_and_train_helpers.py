"""Data versioning/splitting, threshold tuning, metrics, promotion rule."""

import numpy as np
import pytest

from plotgenre.data.split import make_splits, select_version
from plotgenre.models.evaluate import decide_promotion
from plotgenre.models.train import (apply_threshold, build_candidate, multilabel_metrics,
                                    tune_threshold)

pytestmark = pytest.mark.unit


def test_select_version(corpus):
    v1 = select_version(corpus, "v1", 2000)
    v2 = select_version(corpus, "v2", 2000)
    assert (v1["year"] < 2000).all() and len(v2) == len(corpus)
    with pytest.raises(ValueError):
        select_version(corpus, "v9", 2000)


def test_make_splits_sizes_and_disjoint(corpus):
    parts = make_splits(corpus, 0.2, 0.1, seed=1)
    ids = [set(p["wiki_id"]) for p in parts.values()]
    assert sum(len(p) for p in parts.values()) == len(corpus)
    assert not (ids[0] & ids[1]) and not (ids[0] & ids[2]) and not (ids[1] & ids[2])
    assert abs(len(parts["test"]) - 120) <= 2


def test_make_splits_is_reproducible(corpus):
    a = make_splits(corpus, 0.2, 0.1, seed=3)["test"]["wiki_id"].tolist()
    b = make_splits(corpus, 0.2, 0.1, seed=3)["test"]["wiki_id"].tolist()
    assert a == b


def test_apply_threshold_never_returns_empty_rows():
    proba = np.array([[0.1, 0.2], [0.9, 0.6]])
    pred = apply_threshold(proba, 0.5)
    assert pred.tolist() == [[0, 1], [1, 1]]


def test_tune_threshold_picks_best():
    y = np.array([[1, 0], [0, 1]])
    proba = np.array([[0.4, 0.1], [0.1, 0.4]])
    thr, score = tune_threshold(y, proba, [0.3, 0.5])
    assert thr == 0.3 and score == pytest.approx(1.0)


def test_multilabel_metrics_perfect():
    y = np.array([[1, 0], [0, 1]])
    m = multilabel_metrics(y, y, "t_")
    assert m["t_micro_f1"] == 1.0 and m["t_hamming_loss"] == 0.0


def test_build_candidate_unknown():
    with pytest.raises(ValueError):
        build_candidate("xgboost", {}, 0)


@pytest.mark.parametrize("new,champ,ok", [(0.30, None, False), (0.6, None, True),
                                          (0.6, 0.65, False), (0.65, 0.65, True),
                                          (0.7, 0.65, True)])
def test_decide_promotion(new, champ, ok):
    assert decide_promotion(new, champ, 0.40)[0] is ok
