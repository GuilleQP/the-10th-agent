"""Shared, negation-aware stance scoring from ``[POSITION]`` keywords.

Plain substring matching mis-scores negations: ``"visible"`` is a substring of
``"not visible"``, so a converted agent ("the wall is *not visible*") would match
the *false* keyword ``"visible"``. We therefore ignore any keyword occurrence
that is immediately preceded by a negation cue.
"""

from __future__ import annotations

import re

_NEG_WORDS = {"not", "no", "never", "cannot", "without", "none", "neither", "nor"}
_WORD_RE = re.compile(r"[a-z']+")


def _negated(low: str, start: int) -> bool:
    """True if the match at ``start`` is negated by one of the prior ~2 words."""
    prefix = low[max(0, start - 24):start]
    words = _WORD_RE.findall(prefix)
    return any(w in _NEG_WORDS or w.endswith("n't") for w in words[-2:])


def keyword_match(text: str, keywords: list[str]) -> bool:
    """True if any keyword appears in ``text`` in a non-negated position."""
    low = text.lower()
    for kw in keywords:
        k = kw.lower()
        idx = low.find(k)
        while idx != -1:
            if not _negated(low, idx):
                return True
            idx = low.find(k, idx + 1)
    return False


def classify_stance(text: str, truth_kw: list[str], false_kw: list[str]) -> str:
    """Classify a position as ``truth`` / ``false`` / ``unknown``."""
    is_truth = keyword_match(text, truth_kw)
    is_false = keyword_match(text, false_kw)
    if is_truth and not is_false:
        return "truth"
    if is_false and not is_truth:
        return "false"
    return "unknown"
