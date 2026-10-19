"""Similarity of two texts from their term counts: cosine on raw counts (the rank measure) and
Jaccard on the word sets.

Raw term frequency, no weighting by how rare a word is across filings: the weight would depend on
the corpus the night happens to hold, so a value could change without either text changing. The
sums are exact integer sums and one square root of an exact product, so the result does not
depend on insertion order or the platform, and identical texts give exactly 1 (checked, as the
product of large squares can pass 2^53). Both measures are in
[0, 1]; a text with no words has no similarity (``None``), never zero.
"""

import math
from collections.abc import Mapping


def term_cosine(a: Mapping[str, int], b: Mapping[str, int]) -> float | None:
    """Cosine of the two count vectors; ``None`` when either has no words."""
    square_a = sum(n * n for n in a.values())
    square_b = sum(n * n for n in b.values())
    if square_a == 0 or square_b == 0:
        return None
    if dict(a) == dict(b):
        return 1.0
    dot = sum(a[k] * b[k] for k in a.keys() & b.keys())
    return min(1.0, max(0.0, dot / math.sqrt(square_a * square_b)))


def term_jaccard(a: Mapping[str, int], b: Mapping[str, int]) -> float | None:
    """Size of the common word set over the size of the union; ``None`` when both are empty."""
    union = len(a.keys() | b.keys())
    return None if union == 0 else len(a.keys() & b.keys()) / union


def merge_counts(parts: list[Mapping[str, int]]) -> dict[str, int]:
    """The sum of several count vectors (the composite of a filing's compared items)."""
    out: dict[str, int] = {}
    for part in parts:
        for word, n in part.items():
            out[word] = out.get(word, 0) + n
    return out
