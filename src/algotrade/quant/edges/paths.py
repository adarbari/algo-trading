"""The shape of an edge's results over time (ADR 0064): the cumulative curve of per-window
values, its underwater series and worst episodes, the annualised volatility of the windows, the
pooled lift from a start forward and sums by key (a month).

Pure numpy over arrays the caller has already ordered (by the session each value became known).
A missing value is not a zero: ``cumulative`` and the sums reject a non-finite input rather than
carry it, so the caller drops an unmeasured window and the curve joins its neighbours; an
undefined result (too few windows, no picks) is ``None``.

    cumulative        running sum of the values
    underwater        the curve minus its running high, starting from zero (never above 0)
    top_episodes      the worst peak-to-recovery drops of a curve, deepest first
    annualised_vol    sample standard deviation of the windows times the root of windows a year
    excess_wins       wins above what the base rate predicts, per window
    pooled_lift       win rate minus base rate in points, pooled over windows
    sum_by_key        sum and count of values by an integer key (a month)
"""

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

type Array = npt.NDArray[np.float64]
type ArrayLike = npt.ArrayLike

START = -1  # the peak of an episode that began from the curve's start, before its first point


@dataclass(frozen=True)
class Episode:
    """One drop of a curve: from its high at index ``peak`` (``START``: the curve's start, zero)
    down ``depth`` (a positive amount) to its low at ``trough``, and back to the high at
    ``recovered`` (None: not yet recovered)."""

    peak: int
    trough: int
    recovered: int | None
    depth: float


def _finite(values: ArrayLike) -> Array:
    arr = np.asarray(values, dtype=np.float64).ravel()
    if not np.isfinite(arr).all():
        raise ValueError("a missing value is not a zero: drop the unmeasured windows first")
    return arr


def cumulative(values: ArrayLike) -> Array:
    """The running sum of ``values`` (every one finite)."""
    return np.cumsum(_finite(values))


def underwater(curve: ArrayLike) -> Array:
    """``curve`` minus its running high, the high starting at zero: 0 at a new high, below it
    otherwise."""
    arr = _finite(curve)
    return arr - np.maximum.accumulate(np.concatenate(([0.0], arr)))[1:]


def top_episodes(curve: ArrayLike, k: int = 3) -> list[Episode]:
    """The ``k`` deepest drops of ``curve`` below a high (zero at its start), deepest first, ties
    to the earlier. An episode ends when the curve returns to its high."""
    arr = _finite(curve)
    found: list[Episode] = []
    high, peak = 0.0, START
    trough = -1
    for i, x in enumerate(arr):
        if x >= high:
            if trough >= 0:
                found.append(Episode(peak, trough, i, high - float(arr[trough])))
            high, peak, trough = float(x), i, -1
        elif trough < 0 or x < arr[trough]:
            trough = i
    if trough >= 0:
        found.append(Episode(peak, trough, None, high - float(arr[trough])))
    return sorted(found, key=lambda e: -e.depth)[: max(k, 0)]


def annualised_vol(values: ArrayLike, years: float) -> float | None:
    """The sample standard deviation of ``values`` (one per window) times the root of the
    windows a year over ``years``; None for fewer than two windows or no span."""
    arr = _finite(values)
    if arr.size < 2 or years <= 0.0:
        return None
    return float(arr.std(ddof=1) * math.sqrt(arr.size / years))


def excess_wins(
    pick_hits: ArrayLike, picks: ArrayLike, base_hits: ArrayLike, eligible: ArrayLike
) -> Array:
    """Per window, the picks' wins minus what the window's base rate predicts for that many
    picks: ``pick_hits - picks * base_hits / eligible`` (every window has eligible names)."""
    hits, n, bh, el = (_finite(x) for x in (pick_hits, picks, base_hits, eligible))
    if (el <= 0.0).any():
        raise ValueError("a window with no eligible names has no base rate")
    return hits - n * bh / el


def pooled_lift(
    pick_hits: ArrayLike, picks: ArrayLike, base_hits: ArrayLike, eligible: ArrayLike
) -> float | None:
    """The pooled win rate of the picks minus the pooled base rate, in points; None without
    picks or eligible names."""
    hits, n, bh, el = (_finite(x) for x in (pick_hits, picks, base_hits, eligible))
    if n.sum() <= 0.0 or el.sum() <= 0.0:
        return None
    return float((hits.sum() / n.sum() - bh.sum() / el.sum()) * 100.0)


def sum_by_key(keys: ArrayLike, values: ArrayLike) -> tuple[list[int], Array, list[int]]:
    """``(keys, sums, counts)`` of ``values`` grouped by the integer ``keys``, keys ascending."""
    k = np.asarray(keys, dtype=np.int64).ravel()
    v = _finite(values)
    unique, inverse = np.unique(k, return_inverse=True)
    sums = np.zeros(unique.size)
    np.add.at(sums, inverse, v)
    return [int(x) for x in unique], sums, [int(c) for c in np.bincount(inverse)]
