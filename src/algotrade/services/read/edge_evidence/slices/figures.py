"""One period's figures of a slice row (ADR 0064): the win rate, base rate, lift in points and
trades of a stored row, and whether it is ``thin`` (fewer trades than the verdict needs out of
sample, ``min_oos_trades``). A period with no stored row is ``not_stored``; a hidden copy's
out-of-sample and whole-history periods are ``oos_hidden`` (its served rows hold the in-sample
side only): never a zero. The one place the regime and holding-period rows are built from."""

from dataclasses import dataclass

from algotrade.services.read.edge_evidence.costs import (
    IN_SAMPLE,
    MEASURED,
    NOT_STORED,
    OOS_HIDDEN,
    PERIODS,
    STORED_PERIOD,
)
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.runs import EdgeRow

SLICE_STATES = (MEASURED, NOT_STORED, OOS_HIDDEN)


@dataclass(frozen=True)
class SliceFigure:
    """``period`` (all, in_sample, out_of_sample) of one slice: its ``state`` and, when
    measured, the ``win_rate`` and ``base_rate`` (fractions), ``lift_pts`` (win rate less base
    rate, points), ``trades`` (independent sessions) and ``thin``."""

    period: str
    state: str
    win_rate: float | None
    base_rate: float | None
    lift_pts: float | None
    trades: int | None
    thin: bool


def figure_of(period: str, found: EdgeRow | None, hidden: bool, min_trades: int) -> SliceFigure:
    """``period``'s figure from its stored row ``found`` (None: none stored); ``hidden``: the
    run's out-of-sample result is withheld."""
    if hidden and period != IN_SAMPLE:
        return SliceFigure(period, OOS_HIDDEN, None, None, None, None, False)
    if found is None:
        return SliceFigure(period, NOT_STORED, None, None, None, None, False)
    thin = found.sessions is None or found.sessions < min_trades
    return SliceFigure(
        period,
        MEASURED,
        found.hit_rate,
        found.base_rate,
        runs.lift_points(found.hit_rate, found.base_rate),
        found.sessions,
        thin,
    )


def figures_of(rows: tuple[EdgeRow, ...], hidden: bool, min_trades: int) -> tuple[SliceFigure, ...]:
    """The figures of every period (all, in_sample, out_of_sample) among ``rows``, the stored
    rows of one slice's periods (a moved split's ``split`` row stands for ``frozen``)."""
    by = {STORED_PERIOD[r.slice_kind]: r for r in rows if r.slice_kind in STORED_PERIOD}
    return tuple(figure_of(p, by.get(p), hidden, min_trades) for p in PERIODS)
