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
from dataclasses import dataclass, field, replace
from datetime import date
from functools import partial
from typing import Protocol

import numpy as np

from algotrade.quant.edges.statistics import (
    Moments,
    decile_spread,
    deflated_sharpe,
    effect_vs_moments,
    lift,
    merge_moments,
    pbo_cscv,
    sharpe,
    spread_summary,
)

BUCKETS = 10
PBO_SPLITS = 16


@dataclass(frozen=True)
class Pick:
    """One pick of a screener at a decision session (leg v2, ADR 0064 decision 4): every pick,
    counted or excluded. ``reason`` is ``""`` when counted, else why it is not (``hit``'s
    exclusion reasons, or ``no_entry_bar``: no outcome row at S); ``value`` (oriented, net of the
    document's cost) and ``hit`` only when counted. ``rank``: its place among the session's picks,
    best first, from 1; ``score``: the screen's score at D (read with ``as_of = None``, ADR 0063);
    ``gross``: the stored excess return before cost (a return outcome, counted); ``drawdown``:
    the window's ``fwd_max_drawdown``; ``adv``: ``adv_usd_20d`` at D; ``reference`` / ``touch``:
    an ``expires_otm`` pick's. A value not known is None, never 0."""

    instrument_id: str
    rank: int
    reason: str = ""
    value: float | None = None
    hit: bool = False
    delisted: bool = False
    score: float | None = None
    gross: float | None = None
    drawdown: float | None = None
    adv: float | None = None
    reference: float | None = None
    touch: bool | None = None


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
    deciles: tuple[float, ...] = ()  # the mean of each tenth, best-ranked first; () when unranked
    ranked: int = 0  # eligible names with a rank and a counted outcome
    unscored: int = 0  # eligible names with no score, in sessions whose deciles were ranked
    excluded_score_coverage: int = 0  # 1: too few names scored; picks counted, no deciles
    excluded_unclosed: int = 0  # not set by the harness any more: no row at S is ``no_entry_bar``
    excluded_missing: int = 0
    excluded_coverage: int = (
        0  # 1: the screen's coverage was not COMPLETE; the session is not measured
    )
    excluded_unmeasured: int = 0  # picks whose outcome is UNMEASURED (a flagged bar, ADR 0061)
    unmeasured_base: int = 0  # eligible names with an UNMEASURED outcome (the picks included)
    delisted: int = 0
    pre_snapshot: bool = False
    outside_universe: int = 0  # qualified names the edge's universe does not contain
    no_entry_bar: int = 0  # names eligible at D with no outcome row at S (over the base names)
    pick_reference: tuple[float, ...] = ()  # expires_otm: risk-neutral chance of a hit, per pick
    pick_touches: int = 0  # expires_otm: counted picks whose strike was touched intraday
    no_implied_vol: int = 0  # picks excluded for a missing or invalid implied vol at D
    implied_stored: bool = False  # the outcome's iv_field has a value for some eligible name at D
    picks: tuple[Pick, ...] = ()  # every pick, counted ones aligned with ``pick_values`` (v2)
    # Hits at each level of the site's cost grid (``VerdictSettings.cost_levels_bps``, in the leg
    # key) instead of the document's cost: over every counted eligible name and over the picks;
    # () when the outcome is not a return (cost does not apply) or the session is not measured.
    base_hits_at: tuple[int, ...] = ()
    pick_hits_at: tuple[int, ...] = ()

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
    ranked = [leg.deciles for leg in legs if leg.deciles]
    return SessionStat(
        session=first.session,
        regime=first.regime,
        pick_values=tuple(v for leg in legs for v in leg.pick_values),
        pick_hits=sum(leg.pick_hits for leg in legs),
        rest=merge_moments([leg.rest for leg in legs]),
        base_hits=sum(leg.base_hits for leg in legs),
        top_decile=float(np.mean(tops)) if tops else None,
        spread=float(np.mean(spreads)) if spreads else None,
        deciles=_mean_deciles(ranked),
        ranked=sum(leg.ranked for leg in legs),
        unscored=sum(leg.unscored for leg in legs),
        excluded_score_coverage=sum(leg.excluded_score_coverage for leg in legs),
        excluded_unclosed=sum(leg.excluded_unclosed for leg in legs),
        excluded_missing=sum(leg.excluded_missing for leg in legs),
        excluded_unmeasured=sum(leg.excluded_unmeasured for leg in legs),
        unmeasured_base=sum(leg.unmeasured_base for leg in legs),
        delisted=sum(leg.delisted for leg in legs),
        pre_snapshot=any(leg.pre_snapshot for leg in legs),
        outside_universe=sum(leg.outside_universe for leg in legs),
        no_entry_bar=sum(leg.no_entry_bar for leg in legs),
        pick_reference=tuple(v for leg in legs for v in leg.pick_reference),
        pick_touches=sum(leg.pick_touches for leg in legs),
        no_implied_vol=sum(leg.no_implied_vol for leg in legs),
        implied_stored=any(leg.implied_stored for leg in legs),
        picks=tuple(p for leg in legs for p in leg.picks),
        base_hits_at=_sum_levels([leg.base_hits_at for leg in legs]),
        pick_hits_at=_sum_levels([leg.pick_hits_at for leg in legs]),
    )


def _sum_levels(counts: Sequence[tuple[int, ...]]) -> tuple[int, ...]:
    """Per cost level the sum over the days; () when a day has none (not a return outcome)."""
    if not counts or any(len(c) != len(counts[0]) or not c for c in counts):
        return ()
    return tuple(int(sum(level)) for level in zip(*counts, strict=True))


@dataclass(frozen=True)
class Slice:
    """A set of sessions reported on its own: ``kind`` ("all", "year", "year_part" (a year cut
    by the split: value ``<year>:in_sample`` / ``<year>:out_of_sample``), "regime", "in_sample",
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
    excluded_unmeasured: int = 0  # picks left out: their window held a flagged bar
    unmeasured_base: int = 0  # eligible names left out of the base for the same reason
    deflated_sharpe: float | None = field(default=None)
    trials: int | None = field(default=None)
    pbo: float | None = field(default=None)
    reference_rate: float | None = field(default=None)  # expires_otm: mean risk-neutral N(d2)
    touch_rate: float | None = field(default=None)  # expires_otm: picks whose strike was touched
    in_sample: bool = field(default=False)  # a model screener's fit saw sessions of this slice
    decile_means: tuple[float, ...] = field(default=())  # mean of each tenth, over the sessions
    # that had deciles (BUCKETS values), best-ranked first; () when the slice had none


def decile_means(values_in_rank_order: Sequence[float]) -> tuple[float, ...]:
    """The mean of each tenth of finite values best-ranked first (``BUCKETS`` near-equal runs);
    empty under ``BUCKETS`` values or with a value that is not finite."""
    if decile_spread(values_in_rank_order, BUCKETS) is None:
        return ()
    parts = np.array_split(np.asarray(values_in_rank_order, dtype=np.float64), BUCKETS)
    return tuple(float(p.mean()) for p in parts)


def _mean_deciles(ranked: Sequence[tuple[float, ...]]) -> tuple[float, ...]:
    """The tenth-by-tenth mean of the sessions' decile means; empty when none had any."""
    return tuple(float(x) for x in np.mean(np.array(ranked), axis=0)) if ranked else ()


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
        decile_means=_mean_deciles([r.deciles for r in rows if r.deciles]),
        decile_t=spread_t,
        decile_sessions=spread_n,
        effect_size=effect_vs_moments(pick_values, rest),
        sharpe=sharpe(means),
        unscored=sum(r.unscored for r in rows),
        excluded_score_coverage=sum(r.excluded_score_coverage for r in rows),
        excluded_unclosed=sum(r.excluded_unclosed for r in rows),
        excluded_missing=sum(r.excluded_missing for r in rows),
        excluded_unmeasured=sum(r.excluded_unmeasured for r in rows),
        unmeasured_base=sum(r.unmeasured_base for r in rows),
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


def edge_slices(stats: Sequence[SessionStat], split: date | None, exploratory: bool) -> list[Slice]:
    """The slices of a variant's sessions: all, each year (a year the split falls in also as its
    two ``year_part`` sides) and regime label, and with a split the in-sample and frozen (or
    exploratory) sides."""
    slices = [Slice("all", "all", _always)]
    for year in sorted({s.session.year for s in stats}):
        slices.append(Slice("year", str(year), partial(_in_year, year)))
        if split is not None and date(year, 1, 1) < split <= date(year, 12, 31):
            # a trade sits on the side of its decision session, as in_sample / frozen do
            slices.append(
                Slice("year_part", f"{year}:in_sample", partial(_year_before, year, split))
            )
            slices.append(
                Slice("year_part", f"{year}:out_of_sample", partial(_year_since, year, split))
            )
    for label in sorted({s.regime for s in stats}):
        slices.append(Slice("regime", label, partial(_in_regime, label)))
    if split is not None:  # the edge's frozen_from (fixed, never rolling) or an exploratory split
        slices.append(Slice("in_sample", "in_sample", partial(_before, split)))  # ED8: the IS side
        kind = "split" if exploratory else "frozen"
        slices.append(Slice(kind, kind, partial(_since, split)))
    return slices


def _always(stat: SessionStat) -> bool:
    return True


def _in_year(year: int, stat: SessionStat) -> bool:
    return stat.session.year == year


def _year_before(year: int, day: date, stat: SessionStat) -> bool:
    return _in_year(year, stat) and _before(day, stat)


def _year_since(year: int, day: date, stat: SessionStat) -> bool:
    return _in_year(year, stat) and _since(day, stat)


def _in_regime(label: str, stat: SessionStat) -> bool:
    return stat.regime == label


def _before(day: date, stat: SessionStat) -> bool:
    return stat.session < day


def _since(day: date, stat: SessionStat) -> bool:
    return stat.session >= day


class Scored(Protocol):
    """What the trial statistics read of one variant's result at one horizon (the harness's
    ``VariantResult``)."""

    @property
    def horizon(self) -> int: ...
    @property
    def stats(self) -> tuple["SessionStat", ...]: ...
    @property
    def measures(self) -> tuple["SliceMeasure", ...]: ...


def deflate[R: Scored](results: list[R], trials: int) -> list[R]:
    """The deflated Sharpe ratio, the trial count and PBO on each variant's "all" rows. The
    Sharpe variance across trials is taken within a horizon (windows of other lengths are not
    the same kind of trial)."""
    by_horizon: dict[int, list[R]] = {}
    for r in results:
        by_horizon.setdefault(r.horizon, []).append(r)
    variance, overfit = {}, {}
    for horizon, peers in by_horizon.items():
        sharpes = [p.measures[0].sharpe for p in peers if p.measures[0].sharpe is not None]
        variance[horizon] = float(np.var(sharpes, ddof=1)) if len(sharpes) > 1 else 0.0
        overfit[horizon] = pbo(peers)
    out = []
    for r in results:
        means = [m for m in (s.pick_mean for s in r.stats) if m is not None]
        dsr = deflated_sharpe(means, trials, variance[r.horizon]) if means else None
        deflated = replace(
            r.measures[0], deflated_sharpe=dsr, trials=trials, pbo=overfit[r.horizon]
        )
        out.append(replace(r, measures=(deflated, *r.measures[1:])))  # type: ignore[type-var]
    return out


def pbo(peers: Sequence[Scored]) -> float | None:
    """PBO over the sessions every variant held something at: a session where one held nothing
    is left out, never filled in."""
    if len(peers) < 2:
        return None
    days = sorted({s.session for p in peers for s in p.stats})
    means = [_means(p) for p in peers]
    matrix = np.array([[m.get(d, float("nan")) for m in means] for d in days], dtype=np.float64)
    matrix = matrix.reshape(len(days), len(peers))
    return pbo_cscv(matrix[~np.isnan(matrix).any(axis=1)], PBO_SPLITS)


def _means(result: Scored) -> dict[date, float]:
    """A variant's pick mean per session it held something at (the first stat of a session
    with a mean wins)."""
    means: dict[date, float] = {}
    for s in result.stats:
        if s.pick_mean is not None:
            means.setdefault(s.session, s.pick_mean)
    return means
