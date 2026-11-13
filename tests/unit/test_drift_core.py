"""Drift statistics."""

import math

import pytest

from plotgenre.monitoring.drift_core import (build_reference, js_distance, label_drift,
                                             term_drift, tokenize)

pytestmark = pytest.mark.unit


def test_tokenize_lowercases_and_drops_stopwords_and_short_tokens():
    assert tokenize("The Ghost and a Zombie, x 42 haunt US!") == ["ghost", "zombie", "haunt", "us"]


def test_js_distance_bounds():
    assert js_distance([1, 2, 3], [1, 2, 3]) == pytest.approx(0, abs=1e-6)
    assert js_distance([1, 0], [0, 1]) == pytest.approx(1.0, abs=1e-6)
    d = js_distance([0.5, 0.5], [0.9, 0.1])
    assert 0 < d < 1 and not math.isnan(d)


def test_js_distance_rejects_bad_input():
    with pytest.raises(ValueError):
        js_distance([1, 2], [1])
    with pytest.raises(ValueError):
        js_distance([], [])


def test_term_drift_detects_shift(corpus):
    horror = corpus[corpus.genres.str.contains("Horror")]["text"].tolist()
    other = corpus[~corpus.genres.str.contains("Horror")]["text"].tolist()
    ref = build_reference(horror[:60], top_n=50)
    same = term_drift(ref, horror[60:120])
    shifted = term_drift(ref, other[:60])
    assert shifted > same * 1.5


def test_term_drift_empty_current_is_zero():
    assert term_drift({"ghost": 0.5}, []) == 0.0


def test_label_drift():
    prior = {"Drama": 0.5, "Comedy": 0.5}
    assert label_drift(prior, {"Drama": 10, "Comedy": 10}) == pytest.approx(0, abs=1e-6)
    assert label_drift(prior, {"Drama": 10}) > 0.3
    assert label_drift(prior, {}) == 0.0
