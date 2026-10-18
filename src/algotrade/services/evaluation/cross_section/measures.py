"""The numbers of one edge variant over a set of sessions (ADR 0053), from per-session stats.

A ``SessionStat`` is what one session said about one variant at one horizon: the picks, the
eligible names with a closed outcome, the decile means. ``slice_measures`` pools the stats of
each slice (all, a year, a regime label, the frozen period) into a ``SliceMeasure``, with the
number of independent ``sessions`` beside every number (an event schedule's block of event days
is one session: ``pool_stats``). Values are *oriented* (higher is
better: ``hit.apply_outcome``): the returns of an ``excess_return`` edge, the negated ratio of
a ``below`` one. Every count is explicit; nothing is dropped silently by a statistic.

The trial statistics (Sharpe, deflated Sharpe, PBO) read one value per session: the picks' mean
for a return outcome, the session's excess wins (win rate minus base rate) for an outcome whose
value is not a return, a cushion or a ratio (ADR 0064 amendment 2026-10-11: ``trial_value``).
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
    independent_sessions,
    lift,
    merge_moments,
    overlap_t,
    pbo_cscv,
    sharpe,
    sharpe_t,
    spread_summary,
)

BUCKETS = 10
PBO_SPLITS = 16
UNCOUNTED_BAND = "uncounted"  # the reason of a band name with no counted value (never held)


@dataclass(frozen=True)
class Pick:
    """One pick of a screener at a decision session (leg v2, ADR 0064 decision 4): every pick,
    counted or excluded. ``reason`` is ``""`` when counted, else why it is not (``hit``'s
    exclusion reasons, or ``no_entry_bar``: no outcome row at S); ``value`` (oriented, net of the
    document's cost) and ``hit`` only when counted. ``rank``: its place among the session's picks,
    best first, from 1; ``score``: the screen's score at D (read with ``as_of = None``, ADR 0063);
    ``gross``: the stored excess return before cost (a return outcome, counted); ``drawdown``:
    the window's ``fwd_max_drawdown``; ``adv``: ``adv_usd_20d`` at D; ``reference`` / ``touch``:
    an ``expires_otm`` pick's; ``side``: ``short`` for a name the leg is short (its ``value`` and
    ``hit`` are those of the short: ``hit.apply_outcome``'s ``short_value``). A value not known
    is None, never 0."""

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
    side: str = "long"


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
    siblings_stored: bool = True  # pair_spread: its pair_field has a value for some name at D
    picks: tuple[Pick, ...] = ()  # every pick, counted ones aligned with ``pick_values`` (v2)
    # Hits at each level of the site's cost grid (``VerdictSettings.cost_levels_bps``, in the leg
    # key) instead of the document's cost: over every counted eligible name and over the picks;
    # () when the outcome is not a return (cost does not apply) or the session is not measured.
    base_hits_at: tuple[int, ...] = ()
    pick_hits_at: tuple[int, ...] = ()
    # ``long_short`` only (None for every other side): the net values of the counted short-leg
    # names, ``-excess - cost - borrow`` each; ``pick_values`` are then the long leg's.
    short_values: tuple[float, ...] | None = None
    # Buy/hold bands (ADR 0053 amendment 2026-10-18; ``[outcome] hold_rank``). ``band``: the picks
    # ranked just below the counted ones, ``top_k + 1`` to ``hold_rank`` (a name there is held
    # when the previous session held it); stored with the leg (leg v4). ``banded_values`` and
    # ``round_trips`` are set by the turnover pass (``reporting/turnover.py``), never stored:
    # the oriented net values of the names the band held at this session (each net of its own
    # entry and exit cost) and the round trips of cost they paid in all (an entry or an exit is
    # half). None: no band, every pick pays one round trip.
    band: tuple[Pick, ...] = ()
    banded_values: tuple[float, ...] | None = None
    round_trips: float | None = None
    # ``portfolio_return`` only (ADR 0074): the book's weights at D by instrument id (``CASH`` is
    # the T-bill share), summing to one, stored with the leg (leg v5); ``pick_values`` is then the
    # one session value. ``portfolio_reason``: why a session has no value (the session is then
    # ``excluded_coverage``): a held name or a benchmark constituent with no return at S, no
    # volatility or score to weight by, no bill yield for the cash.
    weights: tuple[tuple[str, float], ...] = ()
    portfolio_reason: str = ""

    @property
    def net_values(self) -> tuple[float, ...]:
        """The values the net series and the break-even are over: the band's held names when a
        band ran, else the counted picks (each net of one round trip)."""
        return self.pick_values if self.banded_values is None else self.banded_values

    @property
    def spread_value(self) -> float | None:
        """A ``long_short`` session's value: the long leg's mean plus the short leg's mean (each
        net of its costs), None unless both legs have a counted name (never half a spread)."""
        if self.short_values is None or not self.pick_values or not self.short_values:
            return None
        return float(np.mean(self.pick_values) + np.mean(self.short_values))

    @property
    def eligible(self) -> int:
        return len(self.pick_values) + self.rest[0]

    @property
    def pick_mean(self) -> float | None:
        """The picks' mean value; a ``long_short`` session's is its spread."""
        if self.short_values is not None:
            return self.spread_value
        return float(np.mean(self.net_values)) if self.net_values else None

    @property
    def excess_wins(self) -> float | None:
        """The session's win rate minus its base rate (fractions); None without a counted pick."""
        if not self.pick_values:
            return None
        return self.pick_hits / len(self.pick_values) - self.base_hits / self.eligible


def trial_value(stat: SessionStat, wins: bool) -> float | None:
    """The one value of a session the trial statistics read (ADR 0064 amendment 2026-10-11): the
    excess wins when ``wins`` (the outcome is not a return: a cushion is not P&L, and what such an
    edge claims is that its picks win more often than the names they were picked from), else the
    picks' mean return; a ``long_short`` session's value is its spread (``spread_value``)."""
    if stat.short_values is not None:
        return stat.spread_value
    return stat.excess_wins if wins else stat.pick_mean


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
        siblings_stored=all(leg.siblings_stored for leg in legs),
        picks=tuple(p for leg in legs for p in leg.picks),
        base_hits_at=_sum_levels([leg.base_hits_at for leg in legs]),
        pick_hits_at=_sum_levels([leg.pick_hits_at for leg in legs]),
        short_values=_pooled_short(legs),
    )


def _pooled_short(legs: Sequence[SessionStat]) -> tuple[float, ...] | None:
    """The short legs of a block of days, None when none of them is a long-short day."""
    if all(leg.short_values is None for leg in legs):
        return None
    return tuple(v for leg in legs for v in leg.short_values or ())


def _sum_levels(counts: Sequence[tuple[int, ...]]) -> tuple[int, ...]:
    """Per cost level the sum over the days; () when a day has none (not a return outcome)."""
    if not counts or any(len(c) != len(counts[0]) or not c for c in counts):
        return ()
    return tuple(int(sum(level)) for level in zip(*counts, strict=True))


@dataclass(frozen=True)
class Slice:
    """A set of sessions reported on its own: ``kind`` ("all", "year", "year_part" (a year cut
    by the split: value ``<year>:in_sample`` / ``<year>:out_of_sample``), "regime", "regime_part"
    (a regime label cut the same way: ``<label>:in_sample`` / ``<label>:out_of_sample``),
    "in_sample", "frozen")."""

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
    sharpe: float | None  # per decision session, not annualised, of ``trial_value``
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
    picks_t: float | None = field(default=None)  # the t-ratio of ``sharpe`` (``sharpe_t``)
    reference_rate: float | None = field(default=None)  # expires_otm: mean risk-neutral N(d2)
    touch_rate: float | None = field(default=None)  # expires_otm: picks whose strike was touched
    in_sample: bool = field(default=False)  # a model screener's fit saw sessions of this slice
    decile_means: tuple[float, ...] = field(default=())  # mean of each tenth, over the sessions
    # that had deciles (BUCKETS values), best-ranked first; () when the slice had none
    # Capacity (ADR 0064 decision 5), over the slice's counted picks: the median 20-day dollar
    # volume of those whose is known, how many are known and how many are below the site floor
    # (``adv_floor``); None where it is not measured (a cost row, a random draw).
    pick_adv_median: float | None = field(default=None)
    pick_adv_known: int | None = field(default=None)
    pick_adv_low: int | None = field(default=None)


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


def _capacity(
    rows: Sequence[SessionStat], floor: float | None
) -> tuple[float | None, int | None, int | None]:
    """``(median, known, low)`` of the ADR 0064 capacity columns over the counted picks of
    ``rows``; all None without a ``floor`` (capacity not asked for)."""
    if floor is None:
        return None, None, None
    known = [p.adv for r in rows for p in r.picks if not p.reason and p.adv is not None]
    median = float(np.median(known)) if known else None
    return median, len(known), sum(1 for a in known if a < floor)


def _measure(
    sl: Slice,
    kept: Sequence[SessionStat],
    in_sample: bool = False,
    adv_floor: float | None = None,
    wins: bool = False,
    horizon: int = 1,
) -> SliceMeasure:
    rows = [r for r in kept if not r.excluded_coverage]
    adv_median, adv_known, adv_low = _capacity(rows, adv_floor)
    picks = sum(len(r.pick_values) for r in rows)
    hits = sum(r.pick_hits for r in rows)
    eligible = sum(r.eligible for r in rows)
    base_hits = sum(r.base_hits for r in rows)
    pick_values = _pooled([r.pick_values for r in rows])
    net = _pooled([r.net_values for r in rows])  # the banded names' when a band ran
    rest = merge_moments([r.rest for r in rows])
    n_ref = sum(len(r.pick_reference) for r in rows)  # picks with an expires_otm reference
    hit_rate, base_rate = _mean(hits, picks), _mean(base_hits, eligible)
    spreads = [r.spread for r in rows if r.spread is not None]
    tops = [r.top_decile for r in rows if r.top_decile is not None]
    spread_mean, _, spread_t, spread_n = spread_summary(spreads)
    # Windows of ``horizon`` sessions started every session overlap: a t-ratio over n of them
    # stands for fewer independent sessions, the count the haircut Sharpe ratio rests on too.
    spread_days = [r.session for r in rows if r.spread is not None]
    spread_t = overlap_t(spread_t, spread_n, independent_sessions(spread_days, horizon))
    values = [(r.session, trial_value(r, wins)) for r in rows]
    means = [m for _, m in values if m is not None]
    value_days = [d for d, m in values if m is not None]
    measure = SliceMeasure(
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
        mean_excess_picks=_mean(float(net.sum()), len(net)),
        bh_mean=_mean(float(pick_values.sum() + rest[0] * rest[1]), eligible),
        top_decile_mean=float(np.mean(tops)) if tops else None,
        decile_spread=spread_mean,
        decile_means=_mean_deciles([r.deciles for r in rows if r.deciles]),
        decile_t=spread_t,
        decile_sessions=spread_n,
        effect_size=effect_vs_moments(pick_values, rest),
        sharpe=sharpe(means),
        picks_t=sharpe_t(means, independent_sessions(value_days, horizon)),
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
        pick_adv_median=adv_median,
        pick_adv_known=adv_known,
        pick_adv_low=adv_low,
    )
    if any(r.short_values is not None for r in rows):
        return _long_short(measure, means)
    if any(r.weights for r in rows):
        return _portfolio(measure)
    return measure


def _portfolio(measure: SliceMeasure) -> SliceMeasure:
    """``measure`` of a ``portfolio_return`` outcome (ADR 0074): the base is the blended benchmark
    itself (a value of zero by construction), so there is no base rate, lift, effect size or
    equal-weight floor (None, never 0); the hit rate is the share of sessions that beat it. The
    decile figures are the screen's ranking over the eligible names, present only when enough were
    ranked."""
    return replace(measure, base_hits=0, base_rate=None, lift=None, bh_mean=None, effect_size=None)


def _long_short(measure: SliceMeasure, spreads: Sequence[float]) -> SliceMeasure:
    """``measure`` of a ``long_short`` outcome (ADR 0053 amendment, outcome sides): a spread has
    no base rate, so the hit rate, base rate, lift, effect size and the equal-weight floor are None
    (never 0; the read model says why), and ``mean_excess_picks`` is the mean session spread, the
    long leg's mean plus the short leg's. ``picks`` are the long leg's; the decile figures and the
    Sharpe ratio and its t are the ranking's and the spread's own."""
    return replace(
        measure,
        hits=0,
        hit_rate=None,
        base_hits=0,
        base_rate=None,
        lift=None,
        mean_excess_picks=float(np.mean(spreads)) if spreads else None,
        bh_mean=None,
        effect_size=None,
    )


COST = "cost"  # slice kind of a cost row; its value is ``<period>:<bp>``
COST_PERIODS = ("all", "in_sample", "frozen", "split")  # the slice kinds a cost row is cut for


@dataclass(frozen=True)
class CostGrid:
    """The costs a return edge is measured at: ``document_bp`` (its own ``cost_bps``, which the
    stored values are net of; None counts as 0) and ``levels`` (the site grid, in bp, in the
    order the legs' ``*_hits_at`` count them)."""

    document_bp: float | None
    levels: tuple[float, ...]
    sign: float = 1.0  # the outcome's orientation: the stored values are ``sign * (gross - cost)``

    @property
    def own(self) -> float:
        return self.document_bp or 0.0


def _level_hits(rows: Sequence[SessionStat], index: int) -> tuple[int, int] | None:
    """``(pick hits, base hits)`` at grid level ``index`` over ``rows``; None when a session did
    not count that level (a leg from before the grid): never a guess."""
    if any(len(r.pick_hits_at) <= index or len(r.base_hits_at) <= index for r in rows):
        return None
    return sum(r.pick_hits_at[index] for r in rows), sum(r.base_hits_at[index] for r in rows)


def _cost_rows(m: SliceMeasure, rows: Sequence[SessionStat], costs: CostGrid) -> list[SliceMeasure]:
    """The cost rows of period ``m`` (ADR 0064 decision 5): per cost level, the document's own
    and each of the grid, the hit rate, base rate, lift and mean excess return net of that cost.
    The means are exact: cost is linear in the mean (the stored values are
    ``sign * (gross - cost)``). The decile spread is cost-invariant (both tenths pay the same
    cost), so a cost row leaves it unset and the reader serves the period's own. Capacity is not
    a cost figure: unset here."""
    measured = [r for r in rows if not r.excluded_coverage]
    share = _trip_share(measured)
    found: dict[float, tuple[int, int]] = {costs.own: (m.hits, m.base_hits)}
    for index, bp in enumerate(costs.levels):
        counted = _level_hits(measured, index)
        if counted is not None and bp != costs.own:
            found[bp] = counted
    out = []
    for bp in sorted(found):
        hits, base_hits = found[bp]
        hit_rate, base_rate = _mean(hits, m.picks), _mean(base_hits, m.eligible)
        out.append(
            replace(
                m,
                top_decile_mean=None,
                decile_spread=None,  # cost-invariant: the period's own row says it
                decile_t=None,
                decile_sessions=0,
                effect_size=None,
                sharpe=None,
                picks_t=None,
                deflated_sharpe=None,
                trials=None,
                pbo=None,
                decile_means=(),
                reference_rate=None,
                touch_rate=None,
                pick_adv_median=None,
                pick_adv_known=None,
                pick_adv_low=None,
                slice_kind=COST,
                slice_value=f"{m.slice_kind}:{bp:g}",
                hits=hits,
                base_hits=base_hits,
                hit_rate=hit_rate,
                base_rate=base_rate,
                lift=lift(hit_rate, base_rate),
                mean_excess_picks=_net(m.mean_excess_picks, costs.own, bp, costs.sign, share),
                bh_mean=_net(m.bh_mean, costs.own, bp, costs.sign),
            )
        )
    return out


def _net(
    mean: float | None, own_bp: float, bp: float, sign: float, share: float = 1.0
) -> float | None:
    """``mean`` (oriented, net of ``own_bp``) as it would be net of ``bp``: ``share`` is the
    round trips of cost each name pays (1 without a band)."""
    return None if mean is None else mean + sign * share * (own_bp - bp) / 1e4


def _trip_share(rows: Sequence[SessionStat]) -> float:
    """The round trips of cost the net values of ``rows`` pay per name: a band's turnover (an
    entry or an exit is half a trip, so a name held through pays none), 1.0 for every pick of a
    run without one. The net mean is linear in the cost with this slope."""
    names = sum(len(r.net_values) for r in rows)
    trips = sum(len(r.pick_values) if r.round_trips is None else r.round_trips for r in rows)
    return trips / names if names else 1.0


def slice_measures(
    rows: Sequence[SessionStat],
    slices: Sequence[Slice],
    model: bool = False,
    frozen_from: date | None = None,
    adv_floor: float | None = None,
    wins: bool = False,
    horizon: int = 1,
) -> list[SliceMeasure]:
    """One ``SliceMeasure`` per slice, in the slices' order, over the stats it keeps. A ``model``
    screener's score was fitted on sessions before ``frozen_from`` (a fitness test): a slice that
    keeps one of them is IN_SAMPLE, whatever its kind (no ``frozen_from``: every slice is).
    ``adv_floor``: the site's capacity floor for the capacity columns (none: not measured);
    ``wins``: the outcome is not a return, so the Sharpe ratio is of the excess wins;
    ``horizon``: the holding period in sessions, which sets how far the windows overlap (the
    t-ratios count independent sessions, ``statistics.window_weights``)."""
    out = []
    for sl in slices:
        kept = [r for r in rows if sl.keep(r)]
        seen = model and (frozen_from is None or any(r.session < frozen_from for r in kept))
        out.append(_measure(sl, kept, seen, adv_floor, wins, horizon))
    return out


def cost_measures(
    rows: Sequence[SessionStat],
    slices: Sequence[Slice],
    measures: Sequence[SliceMeasure],
    costs: CostGrid,
) -> list[SliceMeasure]:
    """The cost rows of a return edge (``slice_kind`` ``cost``), for the all, in-sample and
    frozen (or split) periods among ``slices`` (``measures`` its ``slice_measures``)."""
    return [
        row
        for sl, m in zip(slices, measures, strict=True)
        if sl.kind in COST_PERIODS
        for row in _cost_rows(m, [r for r in rows if sl.keep(r)], costs)
    ]


def edge_slices(stats: Sequence[SessionStat], split: date | None, exploratory: bool) -> list[Slice]:
    """The slices of a variant's sessions: all, each year (a year the split falls in also as its
    two ``year_part`` sides) and regime label (with a split also as its two ``regime_part``
    sides), and with a split the in-sample and frozen (or exploratory) sides."""
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
        if split is not None:  # the label cut by the split, on the decision session's side
            slices.append(
                Slice("regime_part", f"{label}:in_sample", partial(_regime_before, label, split))
            )
            slices.append(
                Slice("regime_part", f"{label}:out_of_sample", partial(_regime_since, label, split))
            )
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


def _regime_before(label: str, day: date, stat: SessionStat) -> bool:
    return _in_regime(label, stat) and _before(day, stat)


def _regime_since(label: str, day: date, stat: SessionStat) -> bool:
    return _in_regime(label, stat) and _since(day, stat)


def _before(day: date, stat: SessionStat) -> bool:
    return stat.session < day


def _since(day: date, stat: SessionStat) -> bool:
    return stat.session >= day


SCREENER = "screener"  # the role of a trial; a baseline is a comparison, never a trial
BASELINE = "baseline"


class Scored(Protocol):
    """What the trial statistics read of one variant's result at one horizon (the harness's
    ``VariantResult``): ``unit`` what its values measure, ``wins`` whether the trial statistics
    read the excess wins (``trial_value``)."""

    @property
    def horizon(self) -> int: ...
    @property
    def role(self) -> str: ...
    @property
    def unit(self) -> str | None: ...
    @property
    def wins(self) -> bool: ...
    @property
    def stats(self) -> tuple["SessionStat", ...]: ...
    @property
    def measures(self) -> tuple["SliceMeasure", ...]: ...


def deflate[R: Scored](results: list[R], trials: int) -> list[R]:
    """The deflated Sharpe ratio, the trial count and PBO on each variant's "all" rows. The peers
    whose Sharpe variance and PBO they read are the screeners at the same horizon whose values
    are in the same unit (ADR 0064 amendment 2026-10-11): a window of another length, a value in
    another unit or a baseline (a comparison, not a trial of the hypothesis) is not the same kind
    of trial. A baseline is deflated against the screeners of its horizon and unit. With fewer
    than two peer Sharpe ratios the variance is ``1 / (T - 1)``, the Sharpe estimator's variance
    under the null over the series' ``T`` sessions, so the trial log's count still deflates; PBO
    of a lone trial is None (nothing to compare, never a baseline)."""
    groups: dict[tuple[int, str | None], list[R]] = {}
    for r in results:
        groups.setdefault((r.horizon, r.unit), []).append(r)
    variance: dict[tuple[int, str | None], float | None] = {}
    overfit = {}
    for key, members in groups.items():
        peers = [p for p in members if p.role == SCREENER]
        sharpes = [p.measures[0].sharpe for p in peers if p.measures[0].sharpe is not None]
        variance[key] = float(np.var(sharpes, ddof=1)) if len(sharpes) > 1 else None
        overfit[key] = pbo(peers)
    out = []
    for r in results:
        key = (r.horizon, r.unit)
        values = [v for v in (trial_value(s, r.wins) for s in r.stats) if v is not None]
        v = variance[key]
        if v is None and len(values) > 1:
            v = 1.0 / (len(values) - 1)  # the null's variance of one trial's Sharpe estimate
        dsr = deflated_sharpe(values, trials, v) if values and v is not None else None
        deflated = replace(r.measures[0], deflated_sharpe=dsr, trials=trials, pbo=overfit[key])
        out.append(replace(r, measures=(deflated, *r.measures[1:])))  # type: ignore[type-var]
    return out


def pbo(peers: Sequence[Scored]) -> float | None:
    """PBO over the sessions every variant held something at: a session where one held nothing
    is left out, never filled in. The peers share a unit, so one reads the series all do."""
    if len(peers) < 2:
        return None
    days = sorted({s.session for p in peers for s in p.stats})
    means = [_values(p) for p in peers]
    matrix = np.array([[m.get(d, float("nan")) for m in means] for d in days], dtype=np.float64)
    matrix = matrix.reshape(len(days), len(peers))
    return pbo_cscv(matrix[~np.isnan(matrix).any(axis=1)], PBO_SPLITS)


def _values(result: Scored) -> dict[date, float]:
    """A variant's ``trial_value`` per session it held something at (the first stat of a
    session with a value wins)."""
    values: dict[date, float] = {}
    for s in result.stats:
        value = trial_value(s, result.wins)
        if value is not None:
            values.setdefault(s.session, value)
    return values
