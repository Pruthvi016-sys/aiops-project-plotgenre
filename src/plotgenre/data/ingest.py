"""Stage 1 - ingest.

Downloads the CMU Movie Summary Corpus (once), safely extracts the two files
we need and runs schema checks on them. Output: ``data/raw/MovieSummaries``.

Run: ``python -m plotgenre.data.ingest`` (DVC does this for you).
"""

from __future__ import annotations

import shutil
import tarfile
import time
import urllib.request
from pathlib import Path

from plotgenre.common.config import project_path, section
from plotgenre.common.logging_utils import get_logger
from plotgenre.common.run_tracker import track_stage

log = get_logger(__name__)

REQUIRED_FILES = ("plot_summaries.txt", "movie.metadata.tsv", "README.txt")
METADATA_COLUMNS = 9  # wiki id, freebase id, name, date, revenue, runtime, langs, countries, genres


class IngestError(RuntimeError):
    """Raised when download, extraction or schema validation fails."""


def download(url: str, dest: Path, timeout_s: int, retries: int = 3) -> Path:
    """Download ``url`` to ``dest`` with retries; skip if already present."""
    if dest.exists() and dest.stat().st_size > 0:
        log.info("archive already present at %s (%.1f MB), skipping download",
                 dest, dest.stat().st_size / 1e6)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    for attempt in range(1, retries + 1):
        try:
            log.info("downloading %s (attempt %d/%d)", url, attempt, retries)
            with urllib.request.urlopen(url, timeout=timeout_s) as resp, tmp.open("wb") as out:
                shutil.copyfileobj(resp, out)
            tmp.replace(dest)
            return dest
        except OSError as exc:
            log.warning("download failed: %s", exc)
            time.sleep(2 * attempt)
    raise IngestError(f"could not download {url} after {retries} attempts")


def safe_extract(archive: Path, out_dir: Path) -> Path:
    """Extract only the required files, rejecting path-traversal entries."""
    target = out_dir / "MovieSummaries"
    target.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar.getmembers():
                name = Path(member.name).name
                if name not in REQUIRED_FILES or not member.isfile():
                    continue
                if ".." in Path(member.name).parts or Path(member.name).is_absolute():
                    raise IngestError(f"unsafe path in archive: {member.name}")
                src = tar.extractfile(member)
                if src is None:
                    raise IngestError(f"cannot read {member.name}")
                with (target / name).open("wb") as dst:
                    shutil.copyfileobj(src, dst)
    except tarfile.TarError as exc:
        raise IngestError(f"corrupt archive {archive}: {exc}") from exc
    return target


def validate_raw(raw_dir: Path) -> dict:
    """Schema checks on the extracted files. Returns simple counts."""
    missing = [f for f in REQUIRED_FILES if not (raw_dir / f).exists()]
    if missing:
        raise IngestError(f"missing files after extraction: {missing}")
    bad_meta, n_meta = 0, 0
    with (raw_dir / "movie.metadata.tsv").open(encoding="utf-8") as handle:
        for line in handle:
            n_meta += 1
            if len(line.rstrip("\n").split("\t")) != METADATA_COLUMNS:
                bad_meta += 1
    n_plots = sum(1 for _ in (raw_dir / "plot_summaries.txt").open(encoding="utf-8"))
    if n_meta == 0 or n_plots == 0:
        raise IngestError("raw files are empty")
    if bad_meta / n_meta > 0.01:
        raise IngestError(f"{bad_meta}/{n_meta} metadata rows have a wrong column count")
    return {"metadata_rows": n_meta, "plot_rows": n_plots, "bad_metadata_rows": bad_meta}


def main() -> None:
    """Entry point for the DVC ``ingest`` stage."""
    cfg = section("ingest")
    with track_stage("ingest") as ctx:
        archive = download(cfg["url"], project_path(cfg["archive_path"]), cfg["timeout_s"])
        raw_dir = safe_extract(archive, project_path(cfg["extract_dir"]))
        counts = validate_raw(raw_dir)
        ctx.set_rows(counts["plot_rows"])
        ctx.add(**counts)
        log.info("ingest complete: %s", counts)


if __name__ == "__main__":
    main()
