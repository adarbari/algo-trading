"""The numbers of one edge variant over a set of sessions (ADR 0053), from per-session stats.

A ``SessionStat`` is what one session said about one variant at one horizon: the picks, the
eligible names with a closed outcome, the decile means. ``slice_measures`` pools the stats of
each slice (all, a year, a regime label, the frozen period) into a ``SliceMeasure``, with the
number of independent ``sessions`` beside every number (an event schedule's block of event days
is one session: ``pool_stats``). Values are *oriented* (higher is
better: ``hit.apply_outcome``): the returns of an ``excess_return`` edge, the negated ratio of
a ``below`` one. Every count is explicit; nothing is dropped silently by a statistic.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from algotrade.quant.edge_statistics import (
    Moments,
    decile_spread,
    effect_vs_moments,
    lift,
    merge_moments,
    sharpe,
    spread_summary,
)

BUCKETS = 10


@dataclass(frozen=True)
class SessionStat:
    """One variant at one session and horizon. Counts are over names with a counted outcome;
    ``excluded_*`` and ``delisted`` are over the picks; ``unscored`` counts measured (ranked)
    sessions only, a session with too few scores has no deciles and counts in
    ``excluded_score_coverage`` instead."""

    session: date
    regime: str  # the session's regime label, "UNKNOWN" when none is stored
    pick_values: tuple[float, ...] = ()  # oriented values of the counted picks
    pick_hits: int = 0
    rest: Moments = (0, 0.0, 0.0)  # (n, mean, m2) of the oriented eligible non-picks (counted)
    base_hits: int = 0  # hits among all counted eligible names (the picks included)
    top_decile: float | None = None  # mean of the best-ranked tenth of the ranked eligible
    spread: float | None = None  # top tenth minus bottom tenth
    ranked: int = 0  # eligible names with a rank and a counted outcome
    unscored: int = 0  # eligible names with no score, in sessions whose deciles were ranked
    excluded_score_coverage: int = 0  # 1: too few names scored; picks counted, no deciles
    excluded_unclosed: int = 0  # not set by the harness any more: no row at S is ``no_entry_bar``
    excluded_missing: int = 0
    excluded_coverage: int = (
        0  # 1: the screen's coverage was not COMPLETE; the session is not measured
    )
    delisted: int = 0
    pre_snapshot: bool = False
    outside_universe: int = 0  # qualified names the edge's universe does not contain
    no_entry_bar: int = 0  # names eligible at D with no outcome row at S (over the base names)
    pick_reference: tuple[float, ...] = ()  # expires_otm: risk-neutral chance of a hit, per pick
    pick_touches: int = 0  # expires_otm: counted picks whose strike was touched intraday

    @property
    def eligible(self) -> int:
        return len(self.pick_values) + self.rest[0]

    @property
    def pick_mean(self) -> float | None:
        return float(np.mean(self.pick_values)) if self.pick_values else None


def pool_stats(legs: Sequence[SessionStat]) -> SessionStat:
    """The block of event days (one decision session each) as one statistic at its first
    day: values and counts added, the decile figures the mean of the days that had them. A
    block with a day the screen could not measure (coverage) is not measured at all."""
    first = legs[0]
    if len(legs) == 1:
        return first
    if any(leg.excluded_coverage for leg in legs):
        return SessionStat(session=first.session, regime=first.regime, excluded_coverage=1)
    tops = [leg.top_decile for leg in legs if leg.top_decile is not None]
    spreads = [leg.spread for leg in legs if leg.spread is not None]
    return SessionStat(
        session=first.session,
        regime=first.regime,
        pick_values=tuple(v for leg in legs for v in leg.pick_values),
        pick_hits=sum(leg.pick_hits for leg in legs),
        rest=merge_moments([leg.rest for leg in legs]),
        base_hits=sum(leg.base_hits for leg in legs),
        top_decile=float(np.mean(tops)) if tops else None,
        spread=float(np.mean(spreads)) if spreads else None,
        ranked=sum(leg.ranked for leg in legs),
        unscored=sum(leg.unscored for leg in legs),
        excluded_score_coverage=sum(leg.excluded_score_coverage for leg in legs),
        excluded_unclosed=sum(leg.excluded_unclosed for leg in legs),
        excluded_missing=sum(leg.excluded_missing for leg in legs),
        delisted=sum(leg.delisted for leg in legs),
        pre_snapshot=any(leg.pre_snapshot for leg in legs),
        outside_universe=sum(leg.outside_universe for leg in legs),
        no_entry_bar=sum(leg.no_entry_bar for leg in legs),
        pick_reference=tuple(v for leg in legs for v in leg.pick_reference),
        pick_touches=sum(leg.pick_touches for leg in legs),
    )


@dataclass(frozen=True)
class Slice:
    """A set of sessions reported on its own: ``kind`` ("all", "year", "regime", "in_sample",
    "frozen")."""

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
    unscored: int
    excluded_score_coverage: int  # sessions with picks counted but no deciles: too few scores
    excluded_unclosed: int
    excluded_missing: int
    excluded_coverage: int  # sessions left out: the screen read incomplete data
    delisted: int
    pre_snapshot_sessions: int
    deflated_sharpe: float | None = field(default=None)
    trials: int | None = field(default=None)
    pbo: float | None = field(default=None)
    reference_rate: float | None = field(default=None)  # expires_otm: mean risk-neutral N(d2)
    touch_rate: float | None = field(default=None)  # expires_otm: picks whose strike was touched
    in_sample: bool = field(default=False)  # a model screener's fit saw sessions of this slice


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


def _measure(sl: Slice, kept: Sequence[SessionStat], in_sample: bool = False) -> SliceMeasure:
    rows = [r for r in kept if not r.excluded_coverage]
    picks = sum(len(r.pick_values) for r in rows)
    hits = sum(r.pick_hits for r in rows)
    eligible = sum(r.eligible for r in rows)
    base_hits = sum(r.base_hits for r in rows)
    pick_values = _pooled([r.pick_values for r in rows])
    rest = merge_moments([r.rest for r in rows])
    n_ref = sum(len(r.pick_reference) for r in rows)  # picks with an expires_otm reference
    hit_rate, base_rate = _mean(hits, picks), _mean(base_hits, eligible)
    spreads = [r.spread for r in rows if r.spread is not None]
    tops = [r.top_decile for r in rows if r.top_decile is not None]
    spread_mean, _, spread_t, spread_n = spread_summary(spreads)
    means = [m for m in (r.pick_mean for r in rows) if m is not None]
    return SliceMeasure(
        slice_kind=sl.kind,
        slice_value=sl.value,
        in_sample=in_sample,
        sessions=len(rows),
        picks=picks,
        hits=hits,
        hit_rate=hit_rate,
        eligible=eligible,
        base_hits=base_hits,
        base_rate=base_rate,
        lift=lift(hit_rate, base_rate),
        mean_excess_picks=_mean(float(pick_values.sum()), picks),
        bh_mean=_mean(float(pick_values.sum() + rest[0] * rest[1]), eligible),
        top_decile_mean=float(np.mean(tops)) if tops else None,
        decile_spread=spread_mean,
        decile_t=spread_t,
        decile_sessions=spread_n,
        effect_size=effect_vs_moments(pick_values, rest),
        sharpe=sharpe(means),
        unscored=sum(r.unscored for r in rows),
        excluded_score_coverage=sum(r.excluded_score_coverage for r in rows),
        excluded_unclosed=sum(r.excluded_unclosed for r in rows),
        excluded_missing=sum(r.excluded_missing for r in rows),
        excluded_coverage=sum(r.excluded_coverage for r in kept),
        delisted=sum(r.delisted for r in rows),
        pre_snapshot_sessions=sum(1 for r in rows if r.pre_snapshot),
        reference_rate=_mean(float(sum(sum(r.pick_reference) for r in rows)), n_ref),
        touch_rate=_mean(sum(r.pick_touches for r in rows), n_ref),
    )


def slice_measures(
    rows: Sequence[SessionStat],
    slices: Sequence[Slice],
    model: bool = False,
    frozen_from: date | None = None,
) -> list[SliceMeasure]:
    """One ``SliceMeasure`` per slice, in the slices' order, over the stats it keeps. A ``model``
    screener's score was fitted on sessions before ``frozen_from`` (a fitness test): a slice that
    keeps one of them is IN_SAMPLE, whatever its kind (no ``frozen_from``: every slice is)."""
    out = []
    for sl in slices:
        kept = [r for r in rows if sl.keep(r)]
        seen = model and (frozen_from is None or any(r.session < frozen_from for r in kept))
        out.append(_measure(sl, kept, seen))
    return out
