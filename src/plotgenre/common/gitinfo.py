"""Git / DVC provenance captured into every MLflow run (reproducibility)."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Dict

from plotgenre.common.config import PROJECT_ROOT


def _git(*args: str) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True,
                             text=True, timeout=10, check=True)
        return out.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return "unknown"


def git_info() -> Dict[str, str]:
    """Commit hash, branch and whether the working tree has uncommitted changes."""
    status = _git("status", "--porcelain", "--untracked-files=no")
    return {
        "git_commit": _git("rev-parse", "HEAD"),
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "git_dirty": "unknown" if status == "unknown" else str(bool(status)).lower(),
    }


def file_md5(path: Path) -> str:
    """MD5 of a file (same hash DVC uses) to pin the exact data a run used."""
    digest = hashlib.md5()  # noqa: S324 - content fingerprint, not security
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
