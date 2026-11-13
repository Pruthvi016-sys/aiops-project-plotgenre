"""Encrypted MLflow pyfunc model, Ray preprocessing and Ray featurisation."""

import json
from types import SimpleNamespace

import pandas as pd
import pytest

from plotgenre.common.crypto import encrypt_object, generate_key
from plotgenre.models.pyfunc_model import PlotGenrePyfunc

pytestmark = pytest.mark.integration


def test_pyfunc_loads_encrypted_model_and_predicts(fitted_model, tmp_path, monkeypatch):
    key = generate_key()
    monkeypatch.setenv("PLOTGENRE_MODEL_KEY", key)
    path = encrypt_object(fitted_model, tmp_path / "model.pkl.enc", key)
    py = PlotGenrePyfunc()
    py.load_context(SimpleNamespace(artifacts={"encrypted_model": str(path)}))
    out = py.predict(None, pd.DataFrame({"text": ["alien spaceship planet robot galaxy future"]}),
                     params={"top_k": 2, "explain": True})
    genres = json.loads(out.loc[0, "genres"])
    assert genres[0]["genre"] == "Science Fiction"
    assert json.loads(out.loc[0, "keywords"])
    with pytest.raises(ValueError):
        py.predict(None, pd.DataFrame({"plot": ["x"]}))


@pytest.fixture(scope="module")
def ray_session():
    ray = pytest.importorskip("ray")
    ray.init(num_cpus=2, include_dashboard=False, ignore_reinit_error=True,
             log_to_driver=False, object_store_memory=200 * 1024 * 1024)
    yield ray
    ray.shutdown()


def test_ray_preprocess_pipeline(tmp_path, corpus, ray_session):
    from plotgenre.data.preprocess import quality_gate, run_pipeline

    raw = tmp_path / "MovieSummaries"
    raw.mkdir()
    sample = corpus.head(80)
    lines = [f"{r.wiki_id}\t{r.text}" for r in sample.itertuples()] + ["garbage-line"]
    (raw / "plot_summaries.txt").write_text("\n".join(lines) + "\n")
    meta = []
    for r in sample.itertuples():
        genres = json.dumps({f"/m/{i}": g + " Film" for i, g in enumerate(r.genres.split("|"))})
        meta.append("\t".join([r.wiki_id, "/m/x", r.title, str(r.year), "", "", "{}", "{}", genres]))
    (raw / "movie.metadata.tsv").write_text("\n".join(meta) + "\n")
    cfg = {"batch_size": 25, "min_words": 30, "max_words": 3000, "min_year": 1900,
           "max_year": 2016, "max_null_fraction": 0.05, "num_cpus": 2}
    kw = {"Horror": ["horror"], "Comedy": ["comedy"]}
    clean, report = run_pipeline(raw, cfg, kw)
    assert report["rows_in"] == 81 and report["reject_reasons"]["malformed_line"] == 1
    assert set(clean.columns) >= {"wiki_id", "text", "year", "genres"}
    assert clean["genres"].str.split("|").explode().isin(["Horror", "Comedy"]).all()
    assert report["throughput_rows_per_s"] > 0
    quality_gate(report, cfg, kw)


def test_ray_parallel_transform_matches_sequential(corpus, ray_session):
    from plotgenre.data.featurize import build_vectorizer, parallel_transform

    cfg = {"max_features": 500, "ngram_max": 1, "min_df": 1, "max_df": 1.0, "sublinear_tf": True}
    vec = build_vectorizer(cfg).fit(corpus["text"])
    texts = corpus["text"].tolist()
    par = parallel_transform(vec, texts, chunk_size=97)
    seq = vec.transform(texts)
    assert par.shape == seq.shape and abs(par - seq).max() < 1e-6


def test_quality_gate_rejects_bad_data():
    from plotgenre.data.preprocess import DataQualityError, quality_gate

    cfg = {"max_null_fraction": 0.05}
    with pytest.raises(DataQualityError):
        quality_gate({"malformed_fraction": 0.5, "genre_counts": {"A": 1}, "rows_out": 1},
                     cfg, {"A": []})
    with pytest.raises(DataQualityError):
        quality_gate({"malformed_fraction": 0.0, "genre_counts": {}, "rows_out": 1},
                     cfg, {"A": []})
