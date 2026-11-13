"""Shared fixtures: a small synthetic corpus so tests never need the real dataset."""

import os
import random

import pandas as pd
import pytest

os.environ.setdefault("DISABLE_PUSHGATEWAY", "1")
os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("RAY_USAGE_STATS_ENABLED", "0")

GENRE_WORDS = {
    "Horror": "ghost haunted blood scream demon curse night terror killer zombie",
    "Comedy": "funny wedding prank hilarious awkward party joke mishap goofy laugh",
    "Romance": "love kiss romance heart wedding passion couple affair date marry",
    "Action": "fight explosion chase gun mission soldier battle rescue weapon agent",
    "Crime": "police detective robbery gang murder heist drug mob criminal prison",
    "Science Fiction": "alien spaceship planet robot future galaxy laboratory clone space orbit",
}
LABELS = sorted(GENRE_WORDS)


def make_plot(rng, genres, n_words=60):
    pool = " ".join(GENRE_WORDS[g] for g in genres).split()
    filler = "the man woman city story finally discovers family friend house town".split()
    return " ".join(rng.choice(pool) if rng.random() < 0.6 else rng.choice(filler)
                    for _ in range(n_words))


@pytest.fixture(scope="session")
def corpus():
    """DataFrame shaped like data/processed/movies.parquet (600 rows)."""
    rng = random.Random(7)
    rows = []
    for i in range(600):
        k = 1 if rng.random() < 0.6 else 2
        genres = sorted(rng.sample(LABELS, k))
        rows.append({"wiki_id": str(1000 + i), "title": f"Film {i}",
                     "year": rng.randint(1950, 2012), "text": make_plot(rng, genres),
                     "n_words": 60, "genres": "|".join(genres)})
    return pd.DataFrame(rows)


@pytest.fixture(scope="session")
def fitted_model(corpus):
    """A small trained GenreModel (logreg) on the synthetic corpus."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.multiclass import OneVsRestClassifier
    from sklearn.preprocessing import MultiLabelBinarizer

    from plotgenre.models.explain import extract_weights
    from plotgenre.models.pyfunc_model import GenreModel

    vec = TfidfVectorizer(min_df=1).fit(corpus["text"])
    mlb = MultiLabelBinarizer(classes=LABELS)
    y = mlb.fit_transform(corpus["genres"].str.split("|"))
    clf = OneVsRestClassifier(LogisticRegression(max_iter=500)).fit(vec.transform(corpus["text"]), y)
    return GenreModel(vec, clf, LABELS, 0.3, extract_weights(clf), name="logreg")
