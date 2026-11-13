"""Pure, side-effect-free cleaning and validation functions.

Kept separate from the Ray pipeline so they can be unit tested in isolation
and reused by the gateway for online input validation.
"""

from __future__ import annotations

import json
import re
from typing import Dict, Iterable, List, Optional

_REF_RE = re.compile(r"\[\d+\]|\{\{.*?\}\}")          # wiki references / templates
_URL_RE = re.compile(r"https?://\S+")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_YEAR_RE = re.compile(r"^(\d{4})")


def clean_text(text: Optional[str]) -> str:
    """Normalise a plot summary: strip markup, URLs, references and whitespace.

    Case is preserved for display; the vectoriser lower-cases internally.
    """
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = _URL_RE.sub(" ", text)
    text = _REF_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def word_count(text: str) -> int:
    """Number of whitespace-separated tokens."""
    return len(text.split()) if text else 0


def parse_year(release_date: Optional[str]) -> Optional[int]:
    """Extract a 4-digit year from values like ``1999``, ``1999-05`` or ``1999-05-21``."""
    if not release_date:
        return None
    match = _YEAR_RE.match(release_date.strip())
    return int(match.group(1)) if match else None


def parse_freebase_genres(raw: Optional[str]) -> List[str]:
    """Parse the JSON dict ``{"/m/xxx": "Genre", ...}`` into a list of genre names."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    return [str(v) for v in data.values() if v]


def map_genres(raw_genres: Iterable[str], keywords: Dict[str, List[str]]) -> List[str]:
    """Map raw Freebase genres onto the target genre set by keyword match.

    Example: ``["Romantic comedy"]`` -> ``["Comedy", "Romance"]``.
    Returned list is sorted and de-duplicated.
    """
    lowered = [g.lower() for g in raw_genres]
    labels = set()
    for target, words in keywords.items():
        if any(w.lower() in g for g in lowered for w in words):
            labels.add(target)
    return sorted(labels)


def validate_record(text: str, year: Optional[int], labels: List[str],
                    min_words: int, max_words: int, min_year: int,
                    max_year: int) -> Optional[str]:
    """Return ``None`` if the record is valid, else a short rejection reason."""
    if not text:
        return "empty_text"
    n_words = word_count(text)
    if n_words < min_words:
        return "too_short"
    if n_words > max_words:
        return "too_long"
    if year is None:
        return "missing_year"
    if not (min_year <= year <= max_year):
        return "year_out_of_range"
    if not labels:
        return "no_target_genre"
    return None
