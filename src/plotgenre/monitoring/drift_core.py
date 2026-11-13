"""Dependency-free drift statistics (pure Python).

Shared by the offline ``drift_check`` DVC stage and the online FastAPI
gateway, which is why it only uses the standard library.

Signals
-------
* **term drift** - Jensen-Shannon *distance* (0 = identical, 1 = disjoint)
  between the document-frequency distributions of the reference vocabulary in
  the reference texts vs. the current texts.
* **label drift** - JS distance between the training genre prior and the
  distribution of predicted genres (online only).

``drift_score`` = term drift divided by the *noise floor* (term drift between the
reference and a same-size sample of held-out reference data). A score of ~1
means "as different as random sampling"; the threshold is a ratio (e.g. 1.5).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, Iterable, List, Sequence

TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z]+")
STOP_WORDS = frozenset("""
a about above after again against all also am an and any are as at be because been
before being below between both but by can could did do does doing down during each
few for from further had has have having he her here hers herself him himself his how
i if in into is it its itself just me more most my myself no nor not now of off on
once only or other our ours ourselves out over own same she should so some such than
that the their theirs them themselves then there these they this those through to too
under until up very was we were what when where which while who whom why will with
would you your yours yourself yourselves one two later however back away tells takes
""".split())


def tokenize(text: str) -> List[str]:
    """Lower-case word tokens without stop words (mirrors the TF-IDF tokeniser)."""
    return [t for t in (m.lower() for m in TOKEN_RE.findall(text or ""))
            if t not in STOP_WORDS]


def doc_frequency(texts: Iterable[str]) -> Counter:
    """Number of documents each term appears in."""
    counts: Counter = Counter()
    for text in texts:
        counts.update(set(tokenize(text)))
    return counts


def build_reference(texts: Sequence[str], top_n: int = 2000) -> Dict[str, float]:
    """Reference profile: top-``top_n`` terms -> document-frequency share."""
    df = doc_frequency(texts)
    n_docs = max(len(texts), 1)
    return {term: count / n_docs for term, count in df.most_common(top_n)}


def _normalise(values: Sequence[float]) -> List[float]:
    total = sum(values)
    return [v / total for v in values] if total > 0 else [1.0 / len(values)] * len(values)


def js_distance(p: Sequence[float], q: Sequence[float], eps: float = 1e-12) -> float:
    """Jensen-Shannon distance (base 2) between two non-negative vectors."""
    if len(p) != len(q) or not p:
        raise ValueError("vectors must be non-empty and of equal length")
    p, q = _normalise(p), _normalise(q)
    m = [(a + b) / 2 for a, b in zip(p, q)]

    def kl(x, y):
        return sum(a * math.log2((a + eps) / (b + eps)) for a, b in zip(x, y) if a > 0)

    return math.sqrt(max(0.5 * kl(p, m) + 0.5 * kl(q, m), 0.0))


def term_drift(reference: Dict[str, float], texts: Sequence[str]) -> float:
    """JS distance between reference and current doc-frequency over reference terms."""
    if not texts:
        return 0.0
    terms = list(reference)
    df = doc_frequency(texts)
    n_docs = len(texts)
    current = [df.get(t, 0) / n_docs for t in terms]
    return js_distance([reference[t] for t in terms], current)


def label_drift(prior: Dict[str, float], predicted_counts: Dict[str, int]) -> float:
    """JS distance between training label prior and observed predicted labels."""
    labels = sorted(prior)
    if sum(predicted_counts.get(g, 0) for g in labels) == 0:
        return 0.0
    return js_distance([prior[g] for g in labels],
                       [predicted_counts.get(g, 0) for g in labels])
