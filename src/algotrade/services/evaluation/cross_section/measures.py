"""The numbers of one edge variant over a set of sessions (ADR 0053), from per-session stats.

A ``SessionStat`` is what one session said about one variant at one horizon: the picks, the
eligible names with a closed outcome, the decile means. ``slice_measures`` pools the stats of
each slice (all, a year, a regime label, the frozen period) into a ``SliceMeasure``, with the
number of independent ``sessions`` beside every number. Values are *oriented* (higher is
better: ``hit.apply_outcome``): the returns of an ``excess_return`` edge, the negated ratio of
a ``below`` one. Every count is explicit; nothing is dropped silently by a statistic.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from algotrade.quant.edge_statistics import (
    decile_spread,
    lift,
    sharpe,
    spread_summary,
    standardised_effect,
)

BUCKETS = 10


@dataclass(frozen=True)
class SessionStat:
    """One variant at one session and horizon. Counts are over names with a counted outcome;
    ``excluded_*`` and ``delisted`` are over the picks."""

    session: date
    regime: str  # the session's regime label, "UNKNOWN" when none is stored
    pick_values: tuple[float, ...] = ()  # oriented values of the counted picks
    pick_hits: int = 0
    rest_values: tuple[float, ...] = ()  # oriented values of the eligible non-picks (counted)
    base_hits: int = 0  # hits among all counted eligible names (the picks included)
    top_decile: float | None = None  # mean of the best-ranked tenth of the ranked eligible
    spread: float | None = None  # top tenth minus bottom tenth
    ranked: int = 0  # eligible names with a rank and a counted outcome
    excluded_unclosed: int = 0
    excluded_missing: int = 0
    excluded_coverage: int = (
        0  # 1: the screen's coverage was not COMPLETE; the session is not measured
    )
    delisted: int = 0
    pre_snapshot: bool = False
    outside_universe: int = 0  # qualified names the edge's universe does not contain

    @property
    def eligible(self) -> int:
        return len(self.pick_values) + len(self.rest_values)

    @property
    def pick_mean(self) -> float | None:
        return float(np.mean(self.pick_values)) if self.pick_values else None


@dataclass(frozen=True)
class Slice:
    """A set of sessions reported on its own: ``kind`` ("all", "year", "regime", "frozen")."""

    kind: str
    value: str
    keep: Callable[[SessionStat], bool]


@dataclass(frozen=True)
class SliceMeasure:
    slice_kind: str
    slice_value: str
    sessions: int
    picks: int
    hits: int
    hit_rate: float | None
    eligible: int
    base_hits: int
    base_rate: float | None
    lift: float | None
    mean_excess_picks: float | None
    bh_mean: float | None  # the equal-weight mean over every eligible name: the floor
    top_decile_mean: float | None
    decile_spread: float | None
    decile_t: float | None
    decile_sessions: int
    effect_size: float | None
    sharpe: float | None  # of the per-session mean of the picks, not annualised
    excluded_unclosed: int
    excluded_missing: int
    excluded_coverage: int  # sessions left out: the screen read incomplete data
    delisted: int
    pre_snapshot_sessions: int
    deflated_sharpe: float | None = field(default=None)
    trials: int | None = field(default=None)
    pbo: float | None = field(default=None)


def decile_means(values_in_rank_order: Sequence[float]) -> tuple[float, float] | None:
    """``(top tenth mean, top minus bottom tenth)`` of finite values best-ranked first; None
    under ``BUCKETS`` values."""
    spread = decile_spread(values_in_rank_order, BUCKETS)
    if spread is None:
        return None
    return float(np.mean(np.array_split(np.asarray(values_in_rank_order), BUCKETS)[0])), spread


def _mean(total: float, count: int) -> float | None:
    return total / count if count else None


def _pooled(chunks: Sequence[Sequence[float]]) -> np.ndarray:
    return np.array([v for chunk in chunks for v in chunk], dtype=np.float64)


def _measure(sl: Slice, kept: Sequence[SessionStat]) -> SliceMeasure:
    rows = [r for r in kept if not r.excluded_coverage]
    picks = sum(len(r.pick_values) for r in rows)
    hits = sum(r.pick_hits for r in rows)
    eligible = sum(r.eligible for r in rows)
    base_hits = sum(r.base_hits for r in rows)
    pick_values = _pooled([r.pick_values for r in rows])
    rest_values = _pooled([r.rest_values for r in rows])
    hit_rate, base_rate = _mean(hits, picks), _mean(base_hits, eligible)
    spreads = [r.spread for r in rows if r.spread is not None]
    tops = [r.top_decile for r in rows if r.top_decile is not None]
    spread_mean, _, spread_t, spread_n = spread_summary(spreads)
    means = [m for m in (r.pick_mean for r in rows) if m is not None]
    return SliceMeasure(
        slice_kind=sl.kind,
        slice_value=sl.value,
        sessions=len(rows),
        picks=picks,
        hits=hits,
        hit_rate=hit_rate,
        eligible=eligible,
        base_hits=base_hits,
        base_rate=base_rate,
        lift=lift(hit_rate, base_rate),
        mean_excess_picks=_mean(float(pick_values.sum()), picks),
        bh_mean=_mean(float(pick_values.sum() + rest_values.sum()), eligible),
        top_decile_mean=float(np.mean(tops)) if tops else None,
        decile_spread=spread_mean,
        decile_t=spread_t,
        decile_sessions=spread_n,
        effect_size=standardised_effect(pick_values, rest_values),
        sharpe=sharpe(means),
        excluded_unclosed=sum(r.excluded_unclosed for r in rows),
        excluded_missing=sum(r.excluded_missing for r in rows),
        excluded_coverage=sum(r.excluded_coverage for r in kept),
        delisted=sum(r.delisted for r in rows),
        pre_snapshot_sessions=sum(1 for r in rows if r.pre_snapshot),
    )


def slice_measures(rows: Sequence[SessionStat], slices: Sequence[Slice]) -> list[SliceMeasure]:
    """One ``SliceMeasure`` per slice, in the slices' order, over the stats it keeps."""
    return [_measure(sl, [r for r in rows if sl.keep(r)]) for sl in slices]
