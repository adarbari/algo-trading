"""Percentile rank of a value inside its cohort (numpy only).

``cohort_percentile`` ranks each value among the known values of its own cohort: the average
rank (ties share it) rescaled to 0 (lowest) .. 1 (highest), ``(rank - 1) / (known - 1)``.
A cohort is an int code per element (-1: the element has no cohort). The result is NaN for an
element whose value is NaN, that has no cohort, or whose cohort has fewer than
``max(min_members, 2)`` known values (a rank among one value is meaningless).
"""

import numpy as np


def cohort_percentile(values: np.ndarray, cohorts: np.ndarray, min_members: int) -> np.ndarray:
    """The percentile rank of each value among the known values of its cohort."""
    vals = np.asarray(values, dtype=float)
    codes = np.asarray(cohorts)
    if vals.shape != codes.shape:
        raise ValueError(f"values {vals.shape} and cohorts {codes.shape} must have one shape")
    out = np.full(vals.shape, np.nan)
    need = max(int(min_members), 2)
    usable = ~np.isnan(vals) & (codes >= 0)
    for code in np.unique(codes[usable]):
        at = np.flatnonzero(usable & (codes == code))
        if len(at) < need:
            continue
        pool = np.sort(vals[at])
        below = np.searchsorted(pool, vals[at], side="left")
        upto = np.searchsorted(pool, vals[at], side="right")
        out[at] = (below + upto - 1) / 2.0 / (len(at) - 1)
    return out
