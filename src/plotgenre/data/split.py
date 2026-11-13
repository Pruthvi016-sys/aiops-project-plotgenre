"""Stage 3 - split.

Selects the rows of the requested *data version* and makes reproducible
train / validation / test splits.

Data versions (by release year, see params.yaml -> split):
    v1 - older films only (year < cutoff_year). Newer films are kept aside and
         used to simulate production drift.
    v2 - all films. This is what the retraining workflow switches to after drift
         on newer films has been detected.

Outputs: ``data/splits/{train,val,test}.parquet`` + ``reports/split_summary.json``.
"""

from __future__ import annotations

import json

import pandas as pd
from sklearn.model_selection import train_test_split

from plotgenre.common.config import project_path, section
from plotgenre.common.logging_utils import get_logger
from plotgenre.common.run_tracker import track_stage

log = get_logger(__name__)
VALID_VERSIONS = ("v1", "v2")


def select_version(df: pd.DataFrame, version: str, cutoff_year: int) -> pd.DataFrame:
    """Return the subset of rows that belongs to ``version``."""
    if version not in VALID_VERSIONS:
        raise ValueError(f"unknown data_version '{version}', expected one of {VALID_VERSIONS}")
    if version == "v1":
        return df[df["year"] < cutoff_year].reset_index(drop=True)
    return df.reset_index(drop=True)


def make_splits(df: pd.DataFrame, test_size: float, val_size: float,
                seed: int) -> dict[str, pd.DataFrame]:
    """Random train/val/test split stratified on the *primary* (first) genre."""
    strat = df["genres"].str.split("|").str[0]
    # Rare primary-genre groups break stratification; merge them.
    counts = strat.value_counts()
    strat = strat.where(strat.map(counts) >= 10, "other")
    train_val, test = train_test_split(df, test_size=test_size, random_state=seed,
                                       stratify=strat)
    rel_val = val_size / (1.0 - test_size)
    strat_tv = strat.loc[train_val.index]
    train, val = train_test_split(train_val, test_size=rel_val, random_state=seed,
                                  stratify=strat_tv)
    return {"train": train.reset_index(drop=True), "val": val.reset_index(drop=True),
            "test": test.reset_index(drop=True)}


def main() -> None:
    """Entry point for the DVC ``split`` stage."""
    cfg = section("split")
    df = pd.read_parquet(project_path("data", "processed", "movies.parquet"))
    with track_stage("split") as ctx:
        subset = select_version(df, cfg["data_version"], cfg["cutoff_year"])
        splits = make_splits(subset, cfg["test_size"], cfg["val_size"], cfg["seed"])
        out_dir = project_path("data", "splits")
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, part in splits.items():
            part.to_parquet(out_dir / f"{name}.parquet", index=False)
        summary = {
            "data_version": cfg["data_version"],
            "cutoff_year": cfg["cutoff_year"],
            "rows_total_processed": len(df),
            "rows_in_version": len(subset),
            "rows_newer_films": int((df["year"] >= cfg["cutoff_year"]).sum()),
            **{f"rows_{k}": len(v) for k, v in splits.items()},
            "year_range": [int(subset["year"].min()), int(subset["year"].max())],
        }
        project_path("reports", "split_summary.json").write_text(json.dumps(summary, indent=2))
        ctx.set_rows(len(subset))
        ctx.add(data_version_rows=len(subset))
        log.info("split summary: %s", summary)


if __name__ == "__main__":
    main()
