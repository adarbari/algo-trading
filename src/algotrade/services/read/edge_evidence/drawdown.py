"""How far an edge's curve fell and how much it moves (ADR 0064, ``EdgeDrawdown``): the underwater
series of the evidence curve (its distance below its running high), its three deepest episodes
with dates, the deepest drop on each side of the split and the annualised volatility of the
windows, in-sample and out-of-sample apart.

The curve adds each window at its weight (windows that overlap are weighted so the same days are
not counted again, see ``evidence_curve``). A drop is measured on the per-window curve, so it
understates a dip INSIDE a window (the Guide says so). The out-of-sample side is its own curve
from its first window (zero), so an out-of-sample drop is never a fall from an in-sample high.
Volatility is the standard deviation of
the windows' values times the root of the independent windows a year: the windows the run
observed a year, never more than the sessions a year allow a window of the holding period (the
windows of an every-session schedule overlap, and counting each as independent would overstate
it). Only a return outcome has a drawdown or a volatility: for ``cushion`` and ``ratio`` its
``state`` is ``not_a_return`` (there is no return to fall: a state with a Guide term, not a data
gap, so no cause chain); with no series at all it is ``not_stored`` and ``unknown`` says why."""

from dataclasses import dataclass
from datetime import date
from typing import Final

from algotrade.quant.edges import paths
from algotrade.quant.realized_vol import TRADING_DAYS
from algotrade.services.read.edge_evidence.series import BasisSeries, Window
from algotrade.services.read.evaluation.verdict import IN_SAMPLE, OUT_OF_SAMPLE
from algotrade.services.read.values import Unknown

MEASURED, NOT_STORED, NOT_A_RETURN = "measured", "not_stored", "not_a_return"
DRAWDOWN_STATES: Final = (MEASURED, NOT_STORED, NOT_A_RETURN)
EPISODES = 3
DAYS_PER_YEAR = 365.25


@dataclass(frozen=True)
class UnderwaterPoint:
    """The curve's distance below its running high at ``exit``: ``depth`` is 0 or negative."""

    exit: date
    depth: float


@dataclass(frozen=True)
class DrawdownEpisode:
    """One drop: from the high at ``peak`` (the curve's first decision for a drop from its
    start) down ``depth`` (positive) to ``trough`` and back to ``recovered`` (None: not yet)."""

    peak: date
    trough: date
    recovered: date | None
    depth: float


@dataclass(frozen=True)
class EdgeDrawdown:
    """The underwater ``points`` and the deepest ``episodes`` of the whole curve; ``max_in_sample``
    and ``max_out_of_sample`` the deepest drop of each side (positive; None: that side has no
    window, or the run has no split); ``vol_in_sample`` and ``vol_out_of_sample`` the annualised
    volatility of the windows (None: fewer than two windows). ``state``: measured,
    not_a_return (the outcome has no return) or not_stored (no series: ``unknown`` says why)."""

    unit: str | None
    points: tuple[UnderwaterPoint, ...] = ()
    episodes: tuple[DrawdownEpisode, ...] = ()
    max_in_sample: float | None = None
    max_out_of_sample: float | None = None
    vol_in_sample: float | None = None
    vol_out_of_sample: float | None = None
    unknown: Unknown | None = None
    state: str = MEASURED


def _vol(windows: list[Window], horizon: int) -> float | None:
    """Annualised volatility of ``windows`` (one side), by the independent windows a year."""
    if len(windows) < 2:
        return None
    days = (windows[-1].row.decision_session - windows[0].row.decision_session).days
    years = days / DAYS_PER_YEAR
    if years <= 0.0:
        return None
    observed = (len(windows) - 1) / years  # intervals, not windows, span the years
    independent = min(observed, TRADING_DAYS / max(horizon, 1))
    return paths.annualised_vol([w.value for w in windows], len(windows) / independent)


def _max_depth(windows: list[Window]) -> float | None:
    """The deepest drop of the curve of ``windows`` alone, from zero at its first window."""
    if not windows:
        return None
    return float(-paths.underwater(paths.cumulative([w.weighted for w in windows])).min())


def load_drawdown(series: BasisSeries | Unknown) -> EdgeDrawdown:
    """The drawdown and volatility of the basis ``series``."""
    if isinstance(series, Unknown):
        return EdgeDrawdown(None, unknown=series, state=NOT_STORED)
    if not series.is_return:
        return EdgeDrawdown(series.unit, state=NOT_A_RETURN)
    windows = list(series.windows)
    if not windows:
        return EdgeDrawdown(series.unit)
    curve = paths.cumulative([w.weighted for w in windows])
    depth = paths.underwater(curve)
    start = windows[0].row.decision_session

    def day(i: int) -> date:
        return start if i == paths.START else windows[i].exit

    episodes = tuple(
        DrawdownEpisode(
            day(e.peak),
            windows[e.trough].exit,
            None if e.recovered is None else windows[e.recovered].exit,
            e.depth,
        )
        for e in paths.top_episodes(curve, EPISODES)
    )
    sides = {side: [w for w in windows if w.period == side] for side in (IN_SAMPLE, OUT_OF_SAMPLE)}
    deepest_before = [
        -float(d) for d, w in zip(depth, windows, strict=True) if w.period == IN_SAMPLE
    ]
    return EdgeDrawdown(
        unit=series.unit,
        points=tuple(
            UnderwaterPoint(w.exit, float(d)) for w, d in zip(windows, depth, strict=True)
        ),
        episodes=episodes,
        max_in_sample=max(deepest_before) if deepest_before else None,
        max_out_of_sample=_max_depth(sides[OUT_OF_SAMPLE]),
        vol_in_sample=_vol(sides[IN_SAMPLE], series.horizon),
        vol_out_of_sample=_vol(sides[OUT_OF_SAMPLE], series.horizon),
    )
