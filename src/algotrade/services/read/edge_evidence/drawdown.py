"""How far an edge's curve fell and how much it moves (ADR 0064, ``EdgeDrawdown``): the underwater
series of the evidence curve (its distance below its running high), its three deepest episodes
with dates, the deepest drop on each side of the split and the annualised volatility of the
windows, in-sample and out-of-sample apart.

A drop is measured on the per-window curve, so it understates a dip INSIDE a window (the Guide
says so). The out-of-sample side is its own curve from its first window (zero), so an
out-of-sample drop is never a fall from an in-sample high. Volatility is the standard deviation of
the windows' values times the root of the independent windows a year: the windows the run
observed a year, never more than the sessions a year allow a window of the holding period (the
windows of an every-session schedule overlap, and counting each as independent would overstate
it). Only a return outcome has a drawdown or a volatility: for ``cushion`` and ``ratio`` it is
``NOT_APPLICABLE`` (there is no return to fall)."""

from dataclasses import dataclass
from datetime import date

from algotrade.quant.edges import paths
from algotrade.quant.realized_vol import TRADING_DAYS
from algotrade.services.read.availability.cause import feature_cause
from algotrade.services.read.edge_evidence.series import BasisSeries, Window
from algotrade.services.read.evaluation.verdict import IN_SAMPLE, OUT_OF_SAMPLE
from algotrade.services.read.values import Unknown, UnknownCode

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
    volatility of the windows (None: fewer than two windows). ``unknown``: why there is none."""

    unit: str | None
    points: tuple[UnderwaterPoint, ...] = ()
    episodes: tuple[DrawdownEpisode, ...] = ()
    max_in_sample: float | None = None
    max_out_of_sample: float | None = None
    vol_in_sample: float | None = None
    vol_out_of_sample: float | None = None
    unknown: Unknown | None = None


def _vol(windows: list[Window], horizon: int) -> float | None:
    """Annualised volatility of ``windows`` (one side), by the independent windows a year."""
    if len(windows) < 2:
        return None
    days = (windows[-1].row.decision_session - windows[0].row.decision_session).days
    years = days / DAYS_PER_YEAR
    if years <= 0.0:
        return None
    observed = len(windows) / years
    independent = min(observed, TRADING_DAYS / max(horizon, 1))
    return paths.annualised_vol([w.value for w in windows], len(windows) / independent)


def _max_depth(windows: list[Window]) -> float | None:
    """The deepest drop of the curve of ``windows`` alone, from zero at its first window."""
    if not windows:
        return None
    return float(-paths.underwater(paths.cumulative([w.value for w in windows])).min())


def load_drawdown(series: BasisSeries | Unknown) -> EdgeDrawdown:
    """The drawdown and volatility of the basis ``series``."""
    if isinstance(series, Unknown):
        return EdgeDrawdown(None, unknown=series)
    if not series.is_return:
        why = feature_cause(
            f"unit:{series.unit}", "this outcome has no return to fall", "NOT_A_RETURN"
        )
        return EdgeDrawdown(series.unit, unknown=Unknown(UnknownCode.NOT_APPLICABLE, why))
    windows = list(series.windows)
    if not windows:
        return EdgeDrawdown(series.unit)
    curve = paths.cumulative([w.value for w in windows])
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
