"""A setup's benchmarks over its own windows (ADR 0088, design 2.6): for a named option sleeve,
the Cboe strategy index it ``tracks`` (``IDX:PUT`` and the like, E8b). Pure over what the harness
read: each window's return set beside the index's over the same window.

The index is total return on its collateral held in bills, so the sleeve's side is its return on
collateral plus the bill's over the hold (``bill``: known at D). The index's return is its level
at the window's exit over its level at entry, both as the series knew them by the run's
``as_of``; a window with either level or the bill missing is left out and counted, never filled.
``tracking_error`` is the sample standard deviation of the differences (per window, not
annualised), beside their mean, the correlation and the windows behind them."""

import math
from collections.abc import Mapping, Sequence
from datetime import date

import numpy as np

NO_LEVEL = "no_index_level"  # the index has no level at the window's entry or exit
NO_BILL = "no_bill"  # no bill rate known at the decision session


def index_tracking(
    windows: Sequence[tuple[date, date, date, float]],
    levels: Mapping[date, float],
    bills: Mapping[date, float],
    index: str,
) -> dict[str, float | int | str | None]:
    """The tracking of ``windows`` (``(decision D, entry S, exit, return on collateral)``) against
    ``index``'s ``levels`` by session, with ``bills`` (the bill's return over the hold, by D)."""
    sleeve, tracked = [], []
    lost = {NO_LEVEL: 0, NO_BILL: 0}
    for decision, entry, exit_, value in windows:
        start, end = levels.get(entry), levels.get(exit_)
        if start is None or end is None or not start > 0:
            lost[NO_LEVEL] += 1
            continue
        if decision not in bills:
            lost[NO_BILL] += 1
            continue
        sleeve.append(value + bills[decision])
        tracked.append(end / start - 1.0)
    diff = np.array(sleeve) - np.array(tracked)
    n = len(diff)
    correlation = (
        float(np.corrcoef(sleeve, tracked)[0, 1])
        if n > 2 and np.std(sleeve) > 0 and np.std(tracked) > 0
        else None
    )
    error = float(np.std(diff, ddof=1)) if n > 1 else None
    return {
        "tracks": index,
        "tracked_windows": n,
        "tracking_error": error if error is None or math.isfinite(error) else None,
        "tracking_mean_difference": float(diff.mean()) if n else None,
        "tracking_correlation": correlation,
        **{f"tracking_lost_{k}": v for k, v in lost.items()},
    }
