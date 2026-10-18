"""The basis's per-session series, valued (ADR 0064): the rows of ``results/edge_series`` the
verdict's basis (screen, holding period) wrote, read only through ``runs.load_run_series`` (the
one reader, which withholds a hidden copy's out-of-sample rows), each measured window valued in
the outcome's ``unit``.

A window is a block of decision sessions whose outcome is known at its ``exit_session``, the x of
every picture. A return outcome (``excess_return``, ``return``) is valued in the picks' mean; any
other (``cushion``, ``ratio``) has no return to add up, so a window is valued in the picks' wins
above what the field's base rate predicts. Windows that overlap (a schedule spaced closer than
the holding period) are weighted so a sum over them is a portfolio of staggered tranches, not the
same days counted again (``Window.weight``). A row that holds no number (``excluded_coverage``,
``lost_input``, ``no_picks``, or a measured row with a field missing) is no window: it is kept
apart as a gap, never valued at zero. Not stored (an older run) is ``NOT_STORED``."""

from dataclasses import dataclass
from datetime import date
from typing import Final

from algotrade.quant.edges import paths
from algotrade.quant.edges.statistics import window_weights
from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.context import Stores
from algotrade.services.read.edge_evidence.basis import OfficialBasis
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.runs import SeriesRow
from algotrade.services.read.evaluation.verdict import ALL, IN_SAMPLE, OUT_OF_SAMPLE
from algotrade.services.read.values import Unknown, UnknownCode

EXCESS_RETURN, RETURN, CUSHION, RATIO, PNL = "excess_return", "return", "cushion", "ratio", "pnl"
RETURN_UNITS: Final = (EXCESS_RETURN, RETURN, PNL)  # an outcome whose windows add up to a return
MEASURED, NO_PICKS = "measured", "no_picks"


@dataclass(frozen=True)
class Window:
    """One measured block: ``row``, its ``period`` (``in_sample`` or ``out_of_sample`` by the
    harness's ``before_split``; ``all`` for a run with no split), ``value`` (the picks' mean in a
    return outcome, else the wins above the base rate), the field's ``base_value`` (the mean of
    every eligible name; None for a non-return outcome or when not stored) and ``weight`` (its
    share when windows are added: ``window_weights``, below 1 where windows overlap)."""

    row: SeriesRow
    period: str
    value: float
    base_value: float | None
    weight: float = 1.0

    @property
    def weighted(self) -> float:
        """``value`` at its ``weight``: what the window adds to a curve, a month or a drop."""
        return self.value * self.weight

    @property
    def exit(self) -> date:
        assert self.row.exit_session is not None  # a window has one
        return self.row.exit_session


@dataclass(frozen=True)
class BasisSeries:
    """The basis's series: ``windows`` in the order their outcomes became known (exit session,
    then decision session) and the ``gaps`` (rows that hold no number) in decision order;
    ``unit`` the outcome's, ``split_from`` the run's split, ``hidden`` a copy's withheld
    out-of-sample result (its rows were never served)."""

    key: tuple[str, int]
    unit: str
    split_from: date | None
    hidden: bool
    windows: tuple[Window, ...]
    gaps: tuple[SeriesRow, ...]

    @property
    def is_return(self) -> bool:
        return self.unit in RETURN_UNITS

    @property
    def horizon(self) -> int:
        return self.key[1]


def period_of(row: SeriesRow, split: date | None) -> str:
    """The side of the split a window's decision session fell on, as the harness decided it."""
    if split is None:
        return ALL
    return IN_SAMPLE if row.before_split else OUT_OF_SAMPLE


def _value(row: SeriesRow, unit: str) -> tuple[float, float | None] | None:
    """``(value, base_value)`` of a measured row, None when a field it needs is not stored."""
    if unit in RETURN_UNITS:
        return None if row.pick_mean is None else (row.pick_mean, row.base_mean)
    counts = (row.pick_hits, row.picks, row.base_hits, row.eligible)
    if any(c is None for c in counts) or not row.eligible:
        return None
    hits, picks, base_hits, eligible = (float(c) for c in counts if c is not None)
    return float(paths.excess_wins([hits], [picks], [base_hits], [eligible])[0]), None


def _window(row: SeriesRow, unit: str, split: date | None, weight: float) -> Window | None:
    if row.status != MEASURED or not (row.picks or 0) > 0 or row.exit_session is None:
        return None
    valued = _value(row, unit)
    if valued is None:
        return None
    return Window(row, period_of(row, split), valued[0], valued[1], weight)


def _unit(rows: list[SeriesRow]) -> str:
    """The outcome's unit: the one its rows state (a row from before it was written: a return)."""
    stated = [r.unit for r in rows if r.unit]
    return max(set(stated), key=stated.count) if stated else EXCESS_RETURN


def load_basis_series(ctx: Stores, basis: OfficialBasis) -> BasisSeries | Unknown:
    """The series of ``basis`` (screen and holding period, never a baseline), or why it has
    none: no run or basis (``basis.unknown``), or an older run that stored no series
    (``NOT_STORED``: re-run the backtest)."""
    if basis.run is None or basis.key is None:
        assert basis.unknown is not None
        return basis.unknown
    mine = [
        r
        for r in runs.load_run_series(ctx, basis.run)
        if r.role != runs.BASELINE and (r.variant, r.horizon_sessions) == basis.key
    ]
    if not mine:
        job = f"edge-eval:{basis.run.edge_id}:{basis.run.owner}"
        why = f"{basis.run.run_id} stored no per-session series for {basis.key[0]}: re-run it"
        return Unknown(UnknownCode.NO_ROW, run_cause(job, why))
    return _series_of(mine, basis.key, basis.split_from, basis.hidden)


def _series_of(
    mine: list[SeriesRow], key: tuple[str, int], split: date | None, hidden: bool
) -> BasisSeries:
    """The windows and gaps of one screener's (or baseline's) rows at one horizon."""
    unit = _unit(mine)
    weights = window_weights((r.decision_session for r in mine), key[1])
    windows = [
        w for r in mine if (w := _window(r, unit, split, weights[r.decision_session])) is not None
    ]
    windows.sort(key=lambda w: (w.exit, w.row.decision_session))
    used = {id(w.row) for w in windows}
    gaps = tuple(r for r in mine if id(r) not in used)
    return BasisSeries(key, unit, split, hidden, tuple(windows), gaps)


def load_baseline_series(ctx: Stores, basis: OfficialBasis) -> tuple[BasisSeries, ...]:
    """The series of each baseline (decoy) the run measured at the basis's holding period, by
    baseline name (the same reader as the basis's own, so a hidden copy's out-of-sample rows are
    withheld here too); none when the run has no basis or stored none."""
    if basis.run is None or basis.key is None:
        return ()
    by: dict[str, list[SeriesRow]] = {}
    for r in runs.load_run_series(ctx, basis.run):
        if r.role == runs.BASELINE and r.horizon_sessions == basis.key[1]:
            by.setdefault(r.variant, []).append(r)
    return tuple(
        _series_of(by[v], (v, basis.key[1]), basis.split_from, basis.hidden) for v in sorted(by)
    )
