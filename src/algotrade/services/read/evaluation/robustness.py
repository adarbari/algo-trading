"""How an edge's out-of-sample lift compares with random picks (``Robustness``, ED8 step 2): the
share of the run's random-pick draws it beats and the draws' lifts binned for the page's
distribution. The draws are stored rows (``results/edge_eval`` role ``random``, drawn by the
harness, ``services/evaluation/cross_section/random_picks.py``); the share is
``quant.edges.statistics.percentile_of``, the one place the verdict's "Beats random picks"
criterion and the page's sentence read it. Never recomputed in the browser."""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from algotrade.quant.edges.statistics import haircut_sharpe, percentile_of
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.runs import Draws

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


@dataclass(frozen=True)
class EdgeHaircut:
    """The Sharpe ratio after the multiple-testing haircut (Harvey and Liu, ADR 0064 decision 8):
    the stored ``sharpe`` (per decision session, not annualised; of the excess wins for an outcome
    that is not a return, ADR 0064 amendment 2026-10-11) over ``sessions`` sessions becomes
    ``haircut_sharpe`` once ``trials`` variants tried are counted, ``cut`` (0 to 1) the share
    lost; ``method`` names the adjustment and ``summary`` is the server's sentence. The same
    adjustment is also made for ``site_trials``, every variant tried across every site edge
    (the programme's own multiple-testing count, ADR 0065 amendment 2026-10-17):
    ``site_haircut_sharpe`` and ``site_cut`` (None where the count is not known)."""

    sharpe: float
    haircut_sharpe: float
    cut: float
    trials: int
    sessions: int
    method: str
    summary: str
    site_trials: int | None = None
    site_haircut_sharpe: float | None = None
    site_cut: float | None = None


BONFERRONI = "bonferroni"  # Holm's value for the best of the trials; the peers' t are not stored


def load_haircut(
    sharpe: float | None,
    sessions: int | None,
    trials: int | None,
    wins: bool = False,
    site_trials: int | None = None,
) -> EdgeHaircut | None:
    """The haircut of the basis's ``sharpe`` over ``sessions`` decision sessions after ``trials``
    variants; None when any is not stored or the Sharpe ratio is not above zero. ``wins``: the
    outcome is not a return, so the Sharpe ratio is of the win rate above the base rate, and the
    sentence says so. ``site_trials``: the variants tried across every site edge, which
    the edge's own count is part of; the larger of the two is adjusted for, beside the edge's."""
    h = haircut_sharpe(sharpe, sessions, trials)
    if h is None or sharpe is None or sessions is None or trials is None:
        return None
    wide = None if not site_trials else haircut_sharpe(sharpe, sessions, max(site_trials, trials))
    across = (
        ""
        if wide is None or site_trials is None
        else f" Counting the {max(site_trials, trials):,} variants tried across every site "
        f"edge it falls to {wide.sharpe:.2f}, a haircut of {wide.cut * 100:.0f}%."
    )
    return EdgeHaircut(
        sharpe=sharpe,
        haircut_sharpe=h.sharpe,
        cut=h.cut,
        trials=trials,
        sessions=sessions,
        method=BONFERRONI,
        summary=(
            f"A Sharpe ratio of {sharpe:.2f} per decision session"
            f"{', of the win rate above the base rate,' if wins else ''} "
            f"falls to {h.sharpe:.2f} after "
            f"{trials:,} variant{'' if trials == 1 else 's'} tried, a haircut of "
            f"{h.cut * 100:.0f}%.{across}"
        ),
        site_trials=None if wide is None else max(site_trials or 0, trials),
        site_haircut_sharpe=None if wide is None else wide.sharpe,
        site_cut=None if wide is None else wide.cut,
    )


def draw_lifts(draws: Draws, horizon: int, variant: str) -> list[float]:
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
    lift: float | None, draws: Draws, horizon: int, variant: str
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
    draws: Draws,
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
