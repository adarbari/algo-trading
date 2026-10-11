"""How an edge's result holds up under trading costs (``EdgeCosts``, ADR 0064 decision 5): for a
return edge, its win rate, base rate, lift and mean excess return at each round-trip cost the
harness measured (the document's own and the site grid) over each period, and the break-even
cost, the round-trip cost at which the picks' mean excess return reaches zero. Pure over the
stored ``cost`` rows (``slice_value`` ``<period>:<bp>``); nothing is recomputed in the browser.

The decile spread does not move with cost (both tenths pay it), so it is stated once per period,
read from the period's own row. A period is ``measured`` or has the state saying why not:
``not_stored`` (an older run, or the period does not exist: no split) or ``oos_hidden`` (a
copy's out-of-sample result is withheld, so the whole-history and out-of-sample periods are too).
An edge whose outcome is not a return has no cost rows: ``not_a_cost_outcome``."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from algotrade.quant.edges.statistics import break_even_cost
from algotrade.services.read.context import Stores
from algotrade.services.read.edge_evidence.rows import BasisRows, load_basis_rows
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.edges import Edge
from algotrade.services.read.evaluation.runs import EdgeRow

ALL, IN_SAMPLE, OUT_OF_SAMPLE = "all", "in_sample", "out_of_sample"
PERIODS: Final = (ALL, IN_SAMPLE, OUT_OF_SAMPLE)
# the stored slice kind of each period; a moved split's ``split`` slice stands for ``frozen``
STORED_PERIOD: Final = {
    "all": ALL,
    "in_sample": IN_SAMPLE,
    "frozen": OUT_OF_SAMPLE,
    "split": OUT_OF_SAMPLE,
}
MEASURED, NOT_STORED, NOT_A_COST_OUTCOME, OOS_HIDDEN = (
    "measured",
    "not_stored",
    "not_a_cost_outcome",
    "oos_hidden",
)
COST_STATES: Final = (MEASURED, NOT_STORED, NOT_A_COST_OUTCOME, OOS_HIDDEN)


@dataclass(frozen=True)
class CostLevel:
    """The figures of one ``period`` at a round-trip cost of ``bp`` basis points; ``assumed``:
    the edge document's own cost, which its verdict and every other figure are net of. Rates are
    fractions; ``lift_pts`` the win rate less the base rate in points; ``mean_excess`` the picks'
    mean return over the benchmark net of ``bp`` (a fraction)."""

    period: str
    bp: float
    assumed: bool
    sessions: int | None
    picks: int | None
    win_rate: float | None
    base_rate: float | None
    lift_pts: float | None
    mean_excess: float | None


@dataclass(frozen=True)
class CostPeriod:
    """One period's ``state``, its ``break_even_bp`` (the cost at which the mean excess return is
    zero) and its ``decile_spread`` (cost-invariant); None where not measured."""

    period: str
    state: str
    break_even_bp: float | None
    decile_spread: float | None


@dataclass(frozen=True)
class EdgeCosts:
    """The cost sensitivity of the basis (``variant`` at ``horizon`` sessions): ``state`` (see
    the module), ``assumed_bp`` the document's own cost, the ``levels`` by period then cost and
    one ``CostPeriod`` per period."""

    state: str
    variant: str | None
    horizon: int | None
    assumed_bp: float
    levels: tuple[CostLevel, ...]
    periods: tuple[CostPeriod, ...]


def _split(value: str) -> tuple[str, float] | None:
    """``(period, bp)`` of a cost row's ``slice_value`` ``<period>:<bp>``; None when malformed or
    for a period the page does not show."""
    stored, _, bp = value.partition(":")
    try:
        return (STORED_PERIOD[stored], float(bp)) if stored in STORED_PERIOD else None
    except ValueError:
        return None


def _level(period: str, bp: float, row: EdgeRow, assumed: float) -> CostLevel:
    return CostLevel(
        period=period,
        bp=bp,
        assumed=bp == assumed,
        sessions=row.sessions,
        picks=row.picks,
        win_rate=row.hit_rate,
        base_rate=row.base_rate,
        lift_pts=runs.lift_points(row.hit_rate, row.base_rate),
        mean_excess=row.mean_excess_picks,
    )


def _period(
    period: str, found: Sequence[tuple[float, EdgeRow]], rows: Sequence[EdgeRow], hidden: bool
) -> CostPeriod:
    if hidden and period != IN_SAMPLE:
        return CostPeriod(period, OOS_HIDDEN, None, None)
    if not found:
        return CostPeriod(period, NOT_STORED, None, None)
    bp, row = min(found, key=lambda f: f[0])  # any row gives it: the cost is linear in the mean
    spread = next(
        (r.decile_spread for r in rows if STORED_PERIOD.get(r.slice_kind) == period), None
    )
    return CostPeriod(period, MEASURED, break_even_cost(row.mean_excess_picks, bp), spread)


def costs_of(basis: BasisRows, assumed_bp: float | None) -> EdgeCosts:
    """The cost sensitivity of ``basis`` (None ``assumed_bp``: the document sets no cost, 0).
    With no cost row the state is ``not_a_cost_outcome`` when the run stored its capacity columns
    (the same run writes both: it wrote no cost row because the outcome is not a return), else
    ``not_stored`` (a run from before the columns, or no rows)."""
    assumed = assumed_bp or 0.0
    plain = [r for r in basis.rows if r.slice_kind != runs.COST]
    cost_rows = [
        (split, r)
        for r in basis.rows
        if r.slice_kind == runs.COST and (split := _split(r.slice_value)) is not None
    ]
    by_period = {
        p: sorted(((bp, r) for (period, bp), r in cost_rows if period == p), key=lambda f: f[0])
        for p in PERIODS
    }
    levels = tuple(_level(p, bp, r, assumed) for p in PERIODS for bp, r in by_period[p])
    periods = tuple(_period(p, by_period[p], plain, basis.hidden) for p in PERIODS)
    if cost_rows:
        state = MEASURED
    elif any(r.pick_adv_known is not None for r in plain):  # written by a run that has cost rows
        state = NOT_A_COST_OUTCOME
    else:
        state = NOT_STORED
    return EdgeCosts(state, basis.variant, basis.horizon, assumed, levels, periods)


def load_edge_costs(
    ctx: Stores, edge: Edge, variant: str | None = None, horizon: int | None = None
) -> EdgeCosts:
    """The cost sensitivity of ``edge``'s official result at the verdict's basis (or the screen
    and holding period named), against the document's own cost."""
    cost = edge.settings.cost_bps if edge.settings is not None else None
    return costs_of(load_basis_rows(ctx, edge, variant, horizon), cost)
