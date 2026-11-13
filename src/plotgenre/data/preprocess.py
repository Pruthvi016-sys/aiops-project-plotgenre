"""Stage 2 - preprocess (Ray Data pipeline).

Ray Data DAG::

    read_text(plot_summaries.txt)
        -> map_batches(parse_plot_lines)        # "id \\t summary" -> columns
        -> map_batches(join_metadata)            # add title, year, raw genres
        -> map_batches(clean_and_validate)       # clean text, map genres, reject reason
        -> filter(valid) -> parquet

Data-quality checks (gate the stage):
* fraction of malformed lines <= ``max_null_fraction``
* every target genre has at least one example
* no duplicated movie ids in the output

Outputs: ``data/processed/movies.parquet`` and ``reports/data_quality.json``
(includes throughput in rows/sec, which is also pushed to Prometheus).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict

import pandas as pd
import ray

from plotgenre.common.config import project_path, section
from plotgenre.common.logging_utils import get_logger
from plotgenre.common.run_tracker import track_stage
from plotgenre.data.cleaning import (clean_text, map_genres, parse_freebase_genres,
                                     parse_year, validate_record, word_count)

log = get_logger(__name__)


class DataQualityError(RuntimeError):
    """Raised when the data fails a quality gate."""


def load_metadata(path: Path) -> pd.DataFrame:
    """Read movie.metadata.tsv (small: ~81k rows) into a DataFrame keyed by wiki id."""
    cols = ["wiki_id", "freebase_id", "title", "release_date", "revenue",
            "runtime", "languages", "countries", "genres_raw"]
    meta = pd.read_csv(path, sep="\t", header=None, names=cols, dtype=str,
                       quoting=3, on_bad_lines="skip")
    meta = meta.dropna(subset=["wiki_id"]).drop_duplicates("wiki_id")
    return meta[["wiki_id", "title", "release_date", "genres_raw"]]


def parse_plot_lines(batch: pd.DataFrame) -> pd.DataFrame:
    """Split raw ``text`` lines into ``wiki_id`` and ``summary``; flag malformed lines."""
    parts = batch["text"].str.split("\t", n=1, expand=True)
    if parts.shape[1] < 2:
        parts[1] = None
    out = pd.DataFrame({"wiki_id": parts[0].str.strip(), "summary": parts[1]})
    out["malformed"] = out["summary"].isna() | ~out["wiki_id"].str.isdigit().fillna(False)
    return out


def make_join_fn(meta_ref: "ray.ObjectRef"):
    """Return a batch function that left-joins metadata held in the object store."""
    def join_metadata(batch: pd.DataFrame) -> pd.DataFrame:
        meta = ray.get(meta_ref)
        return batch.merge(meta, on="wiki_id", how="left")
    return join_metadata


def make_clean_fn(cfg: Dict, keywords: Dict):
    """Return a batch function that cleans text, maps genres and validates rows."""
    def clean_and_validate(batch: pd.DataFrame) -> pd.DataFrame:
        texts, years, labels, reasons, n_words = [], [], [], [], []
        for row in batch.itertuples(index=False):
            if row.malformed:
                texts.append("")
                years.append(None)
                labels.append([])
                reasons.append("malformed_line")
                n_words.append(0)
                continue
            text = clean_text(row.summary)
            year = parse_year(row.release_date if isinstance(row.release_date, str) else None)
            labs = map_genres(parse_freebase_genres(
                row.genres_raw if isinstance(row.genres_raw, str) else None), keywords)
            reason = validate_record(text, year, labs, cfg["min_words"], cfg["max_words"],
                                     cfg["min_year"], cfg["max_year"])
            texts.append(text)
            years.append(year)
            labels.append(labs)
            reasons.append(reason or "")
            n_words.append(word_count(text))
        return pd.DataFrame({
            "wiki_id": batch["wiki_id"].values,
            "title": batch["title"].fillna("").values,
            "year": pd.array(years, dtype="Int64"),
            "text": texts,
            "n_words": n_words,
            "genres": ["|".join(x) for x in labels],
            "reject_reason": reasons,
        })
    return clean_and_validate


def run_pipeline(raw_dir: Path, cfg: Dict, keywords: Dict) -> tuple[pd.DataFrame, Dict]:
    """Execute the Ray pipeline and return (clean_df, quality_report)."""
    if not ray.is_initialized():
        ray.init(num_cpus=cfg.get("num_cpus"), include_dashboard=False,
                 ignore_reinit_error=True, log_to_driver=False,
                 object_store_memory=400 * 1024 * 1024)
    started = time.time()
    meta = load_metadata(raw_dir / "movie.metadata.tsv")
    meta_ref = ray.put(meta)
    batch = cfg["batch_size"]
    ds = (ray.data.read_text(str(raw_dir / "plot_summaries.txt"))
          .map_batches(parse_plot_lines, batch_format="pandas", batch_size=batch)
          .map_batches(make_join_fn(meta_ref), batch_format="pandas", batch_size=batch)
          .map_batches(make_clean_fn(cfg, keywords), batch_format="pandas",
                       batch_size=batch))
    full = ds.to_pandas()
    elapsed = max(time.time() - started, 1e-9)

    rows_in = len(full)
    reasons = full["reject_reason"].replace("", "accepted").value_counts().to_dict()
    malformed = reasons.get("malformed_line", 0)
    clean = full[full["reject_reason"] == ""].drop(columns=["reject_reason"])
    dupes = int(clean["wiki_id"].duplicated().sum())
    # Ray does not guarantee output order; sort so the parquet (and therefore the
    # downstream random split) is byte-for-byte reproducible.
    clean = (clean.drop_duplicates("wiki_id")
             .sort_values("wiki_id", key=lambda s: s.astype("int64"))
             .reset_index(drop=True))
    # Ray returns pyarrow-backed dtypes; normalise to plain dtypes for downstream pandas.
    clean = clean.astype({"wiki_id": str, "title": str, "text": str, "genres": str,
                          "year": "int64", "n_words": "int64"})

    label_counts = (clean["genres"].str.split("|").explode().value_counts().to_dict())
    report = {
        "rows_in": rows_in,
        "rows_out": len(clean),
        "rows_rejected": rows_in - len(clean),
        "reject_reasons": {k: int(v) for k, v in reasons.items()},
        "malformed_fraction": round(malformed / max(rows_in, 1), 5),
        "duplicate_ids_removed": dupes,
        "genre_counts": {k: int(v) for k, v in label_counts.items()},
        "avg_words": round(float(clean["n_words"].mean()), 1) if len(clean) else 0.0,
        "year_min": int(clean["year"].min()) if len(clean) else None,
        "year_max": int(clean["year"].max()) if len(clean) else None,
        "elapsed_s": round(elapsed, 2),
        "throughput_rows_per_s": round(rows_in / elapsed, 1),
        "ray_num_cpus": int(ray.cluster_resources().get("CPU", 0)),
    }
    return clean, report


def quality_gate(report: Dict, cfg: Dict, keywords: Dict) -> None:
    """Fail loudly if the processed data does not meet the quality rules."""
    if report["malformed_fraction"] > cfg["max_null_fraction"]:
        raise DataQualityError(
            f"malformed fraction {report['malformed_fraction']} > {cfg['max_null_fraction']}")
    missing = [g for g in keywords if report["genre_counts"].get(g, 0) == 0]
    if missing:
        raise DataQualityError(f"no examples for genres: {missing}")
    if report["rows_out"] == 0:
        raise DataQualityError("no rows survived cleaning")


def main() -> None:
    """Entry point for the DVC ``preprocess`` stage."""
    cfg = section("preprocess")
    keywords = cfg["genre_keywords"]
    raw_dir = project_path(section("ingest")["extract_dir"], "MovieSummaries")
    out_path = project_path("data", "processed", "movies.parquet")
    with track_stage("preprocess") as ctx:
        clean, report = run_pipeline(raw_dir, cfg, keywords)
        quality_gate(report, cfg, keywords)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        clean.to_parquet(out_path, index=False)
        report_path = project_path("reports", "data_quality.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2))
        ctx.set_rows(report["rows_in"])
        ctx.add(rows_out=report["rows_out"],
                malformed_fraction=report["malformed_fraction"],
                ray_throughput_rows_per_s=report["throughput_rows_per_s"])
        log.info("preprocess: %d -> %d rows at %.0f rows/s", report["rows_in"],
                 report["rows_out"], report["throughput_rows_per_s"])
    ray.shutdown()


if __name__ == "__main__":
    main()
