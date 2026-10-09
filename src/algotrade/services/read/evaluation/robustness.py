"""How an edge's out-of-sample lift compares with random picks (``Robustness``, ED8 step 2): the
share of the run's random-pick draws it beats and the draws' lifts binned for the page's
distribution. The draws are stored rows (``results/edge_eval`` role ``random``, drawn by the
harness, ``services/evaluation/cross_section/random_picks.py``); the share is
``quant.edge_statistics.percentile_of``, the one place the verdict's "Beats random picks"
criterion and the page's sentence read it. Never recomputed in the browser."""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from algotrade.quant.edge_statistics import percentile_of
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.runs import EdgeRow

BINS = 20


@dataclass(frozen=True)
class RobustnessBin:
    """One bin of the draws' lifts: ``start`` (inclusive) to ``end`` (exclusive, inclusive for
    the last bin), ``count`` draws."""

    start: float
    end: float
    count: int


@dataclass(frozen=True)
class Robustness:
    """The edge's out-of-sample ``lift`` among ``draws`` random-pick backtests of the same
    holding period: ``beats`` the share of them it is above (0 to 1, ties half), the draws binned
    best-looking last, and the server's ``summary`` sentence."""

    lift: float
    draws: int
    beats: float
    bins: tuple[RobustnessBin, ...]
    summary: str


def draw_lifts(draws: Sequence[EdgeRow], horizon: int, variant: str) -> list[float]:
    """The lifts of the random draws matched to screener ``variant`` of the edge itself at
    ``horizon`` (a draw with no lift, a base rate of zero, is not a draw)."""
    return [
        d.lift
        for d in draws
        if d.edge_variant == runs.MAIN
        and d.variant == f"{runs.RANDOM}:{variant}"
        and d.horizon_sessions == horizon
        and d.lift is not None
    ]


def beat_share(
    lift: float | None, draws: Sequence[EdgeRow], horizon: int, variant: str
) -> tuple[float | None, int]:
    """``(share of the draws ``lift`` beats, how many draws)``; the share is None without a lift
    or draws."""
    lifts = draw_lifts(draws, horizon, variant)
    return percentile_of(lift, lifts), len(lifts)


def _binned(lifts: Sequence[float], lift: float) -> tuple[RobustnessBin, ...]:
    """``BINS`` equal-width bins over the draws and the edge's own lift (so its marker sits
    inside the axis)."""
    low, high = min(*lifts, lift), max(*lifts, lift)
    if high <= low:
        return (RobustnessBin(low, low + 1.0, len(lifts)),)
    counts, edges = np.histogram(lifts, bins=BINS, range=(low, high))
    return tuple(
        RobustnessBin(float(edges[i]), float(edges[i + 1]), int(counts[i])) for i in range(BINS)
    )


def load_robustness(
    lift: float | None,
    draws: Sequence[EdgeRow],
    horizon: int,
    variant: str,
    trials: int | None,
) -> Robustness | None:
    """The out-of-sample ``lift`` against the draws at ``horizon``; None when the run drew none
    or the edge has no lift. ``trials``: the variants tried (they make the best look better)."""
    share, n = beat_share(lift, draws, horizon, variant)
    if lift is None or share is None:
        return None
    tried = "" if not trials else f" after {trials} variant{'' if trials == 1 else 's'} tried"
    return Robustness(
        lift=lift,
        draws=n,
        beats=share,
        bins=_binned(draw_lifts(draws, horizon, variant), lift),
        summary=f"Beats {share * 100:.0f}% of {n:,} random backtests{tried}.",
    )
