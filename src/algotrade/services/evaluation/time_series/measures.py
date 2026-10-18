"""What a time-series edge measures (ADR 0073): per instrument, the in-window returns against the
out-of-window ones, as the ``SliceMeasure`` rows the verdict already reads.

An observation is a period's raw return and the regime label at its decision session D. A slice
(all, a year, a regime label and, with a split, the in-sample and frozen sides, cut by the
period's decision session) is measured as:

- ``hits`` / ``hit_rate``: the in-window periods with a positive return; ``base_hits`` /
  ``base_rate`` (``eligible``: their number): the same share among the out-of-window ones, so
  ``lift`` and the verdict's win-rate words read as for a cross-section edge
- ``mean_excess_picks`` / ``bh_mean``: the mean in-window and out-of-window return;
  ``decile_spread``: their difference; ``decile_t``: its Welch t-ratio (the verdict's Promising
  t >= 2 and Works t >= 3), read over the independent periods
- ``effect_size``: Hedges' g between the two; ``sharpe`` / ``picks_t``: the in-window returns'
  Sharpe ratio and its t-ratio; ``sessions`` / ``decile_sessions``: the independent windows

Every count is of independent periods: one period is one session, and ``statistics.window_weights``
corrects for periods closer together than the window (the tiling leaves none; an overlapping
placement would be weighted down, never counted twice). ``timing_sharpes`` is the Sharpe ratio of
"long in the window, bills otherwise" against buying and holding, over every period in order.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from functools import partial

import numpy as np

from algotrade.quant.edges.statistics import (
    deflated_sharpe,
    independent_sessions,
    lift,
    overlap_t,
    pbo_cscv,
    sharpe,
    sharpe_t,
    standardised_effect,
    welch_t,
)
from algotrade.services.evaluation.cross_section.measures import PBO_SPLITS, SliceMeasure
from algotrade.services.evaluation.time_series.periods import Period


@dataclass(frozen=True)
class Obs:
    """One period's raw return and its decision session's regime label."""

    period: Period
    value: float
    regime: str


def _mean(x: Sequence[float]) -> float | None:
    return float(np.mean(x)) if len(x) else None


def _share(x: Sequence[float]) -> tuple[int, float | None]:
    hits = sum(v > 0 for v in x)
    return hits, (hits / len(x) if len(x) else None)


def measure(kind: str, value: str, kept: Sequence[Obs], horizon: int) -> SliceMeasure:
    """The measure of the observations ``kept`` for one slice."""
    inside = [o for o in kept if o.period.inside]
    outside = [o for o in kept if not o.period.inside]
    a, b = [o.value for o in inside], [o.value for o in outside]
    ind_in = independent_sessions([o.period.entry for o in inside], horizon)
    ind_out = independent_sessions([o.period.entry for o in outside], horizon)
    diff, t = welch_t(a, b)
    hits, hit_rate = _share(a)
    base_hits, base_rate = _share(b)
    return SliceMeasure(
        slice_kind=kind,
        slice_value=value,
        sessions=ind_in,
        picks=len(a),
        hits=hits,
        hit_rate=hit_rate,
        eligible=len(b),
        base_hits=base_hits,
        base_rate=base_rate,
        lift=lift(hit_rate, base_rate),
        mean_excess_picks=_mean(a),
        bh_mean=_mean(b),
        top_decile_mean=None,
        decile_spread=diff,
        decile_t=overlap_t(t, len(a) + len(b), ind_in + ind_out),
        decile_sessions=ind_in,
        effect_size=standardised_effect(a, b),
        sharpe=sharpe(a),
        unscored=0,
        excluded_score_coverage=0,
        excluded_unclosed=0,
        excluded_missing=0,
        excluded_coverage=0,
        delisted=0,
        pre_snapshot_sessions=0,
        picks_t=sharpe_t(a, ind_in),
    )


def _in_year(year: int, o: Obs) -> bool:
    return o.period.decision.year == year


def _in_regime(label: str, o: Obs) -> bool:
    return o.regime == label


def _slices(
    obs: Sequence[Obs], split: date | None, exploratory: bool
) -> list[tuple[str, str, Callable[[Obs], bool]]]:
    out: list[tuple[str, str, Callable[[Obs], bool]]] = [("all", "all", lambda o: True)]
    for year in sorted({o.period.decision.year for o in obs}):
        out.append(("year", str(year), partial(_in_year, year)))
    for label in sorted({o.regime for o in obs}):
        out.append(("regime", label, partial(_in_regime, label)))
    if split is not None:  # cut by the period's decision session, as the cross-section slices
        out.append(("in_sample", "in_sample", lambda o: o.period.decision < split))
        kind = "split" if exploratory else "frozen"
        out.append((kind, kind, lambda o: o.period.decision >= split))
    return out


def measures(
    obs: Sequence[Obs], horizon: int, split: date | None, exploratory: bool
) -> tuple[SliceMeasure, ...]:
    """One measure per slice of ``obs``, ``all`` first; with no observation just an empty
    ``all`` (sessions 0, every statistic None)."""
    return tuple(
        measure(kind, value, [o for o in obs if keep(o)], horizon)
        for kind, value, keep in _slices(obs, split, exploratory)
    )


def timing_sharpes(
    obs: Sequence[Obs], bills: Mapping[date, float]
) -> dict[str, float | int | None]:
    """The per-period Sharpe ratios of "long in the window, bills otherwise" and of buying and
    holding, over the periods (in order) whose decision session has a bill rate: the first is
    the timing series (the period's return inside a window, the bill's outside), the second the
    return of every period. Both None under two periods or no spread."""
    kept = sorted((o for o in obs if o.period.decision in bills), key=lambda o: o.period.first)
    timed = [o.value if o.period.inside else bills[o.period.decision] for o in kept]
    return {
        "periods": len(kept),
        "timing_sharpe": sharpe(timed),
        "buy_hold_sharpe": sharpe([o.value for o in kept]),
    }


def deflate_trial(
    measure_all: SliceMeasure, in_window: Sequence[float], trials: int, pbo: float | None
) -> SliceMeasure:
    """``measure_all`` (the ``all`` row) with the trial count, the deflated Sharpe ratio of the
    in-window returns (the variance of a lone trial's estimate under the null, ``1 / (T - 1)``,
    as for a cross-section edge) and the PBO among the edge's instruments."""
    n = len(in_window)
    dsr = deflated_sharpe(in_window, trials, 1.0 / (n - 1)) if n > 1 else None
    return replace(measure_all, deflated_sharpe=dsr, trials=trials, pbo=pbo)


def pbo_among(series: Mapping[str, Mapping[date, float]]) -> float | None:
    """PBO over the instruments' in-window returns on the windows every instrument has (one
    left out is dropped for all, never filled); None under two instruments or too few windows."""
    if len(series) < 2:
        return None
    days = sorted(set.intersection(*(set(s) for s in series.values())))
    matrix = np.array([[s[d] for s in series.values()] for d in days], dtype=np.float64)
    return pbo_cscv(matrix.reshape(len(days), len(series)), PBO_SPLITS)
