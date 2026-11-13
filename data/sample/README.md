# Sample data

`movies_sample.parquet` holds 300 cleaned plots (150 released before 2000 and 150 from 2000 on). They come from the CMU Movie Summary Corpus (Bamman, O'Connor and Smith, 2013), which is licensed CC BY-SA 3.0. The text is from Wikipedia.

The schema is the same as `data/processed/movies.parquet` (see docs/LLD.md). The file is stored with **Git LFS**. `scripts/simulate_traffic.py` uses it when the full processed dataset has not been generated yet.

The full dataset is not in Git. `dvc repro` downloads it, and DVC versions it.
