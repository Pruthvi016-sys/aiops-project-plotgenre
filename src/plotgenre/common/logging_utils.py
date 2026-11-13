"""Uniform logging set-up used by every pipeline stage and service.

Logs go to stdout (so ``docker compose logs`` shows them) and, for pipeline
stages, also to ``logs/pipeline.log`` for auditing.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_configured = False


def get_logger(name: str, log_file: str | os.PathLike | None = None) -> logging.Logger:
    """Return a logger configured with a consistent format.

    Args:
        name: Logger name, usually ``__name__``.
        log_file: Optional file to also write logs to.
    """
    global _configured
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger("plotgenre")
    if not _configured:
        root.setLevel(level)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(handler)
        root.propagate = False
        _configured = True
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        already = any(
            isinstance(h, logging.FileHandler) and Path(h.baseFilename) == path.resolve()
            for h in root.handlers
        )
        if not already:
            file_handler = logging.FileHandler(path, encoding="utf-8")
            file_handler.setFormatter(logging.Formatter(_FORMAT))
            root.addHandler(file_handler)
    if not name.startswith("plotgenre"):
        name = f"plotgenre.{name}"
    return logging.getLogger(name)
