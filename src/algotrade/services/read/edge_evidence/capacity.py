"""How much money an edge's picks can take (``EdgeCapacity``, ADR 0064 decision 5): per period,
the median 20-day dollar volume of the picks the harness counted, how many have one stored and
how many trade below the site's floor (``capacity_adv_floor_usd``, ``verdict.toml``). Pure over
the stored ``pick_adv_*`` columns; the floor is applied when the harness computes the
statistics, so a run from before a changed floor still says which floor it used only in its own
count. A period is ``measured``, ``not_stored`` (an older run, no split, or no pick had a stored
volume) or ``oos_hidden`` (a copy's out-of-sample result is withheld)."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from algotrade.config.site.settings import load_verdict
from algotrade.services.read.context import Stores
from algotrade.services.read.edge_evidence.costs import (
    IN_SAMPLE,
    MEASURED,
    NOT_STORED,
    OOS_HIDDEN,
    PERIODS,
    STORED_PERIOD,
)
from algotrade.services.read.edge_evidence.rows import BasisRows, load_basis_rows
from algotrade.services.read.evaluation.edges import Edge
from algotrade.services.read.evaluation.runs import EdgeRow

CAPACITY_STATES: Final = (MEASURED, NOT_STORED, OOS_HIDDEN)


@dataclass(frozen=True)
class CapacityPeriod:
    """One period: ``adv_median`` (dollars, over the ``adv_known`` picks with a stored volume),
    ``adv_low`` of them below the floor, ``picks`` counted in all; None where not measured."""

    period: str
    state: str
    picks: int | None
    adv_median: float | None
    adv_known: int | None
    adv_low: int | None


@dataclass(frozen=True)
class EdgeCapacity:
    """The capacity of the basis (``variant`` at ``horizon`` sessions): ``floor_usd`` the site's
    floor today and one ``CapacityPeriod`` per period (``state`` of the whole: measured when any
    period is)."""

    state: str
    variant: str | None
    horizon: int | None
    floor_usd: float
    periods: tuple[CapacityPeriod, ...]


def _period(period: str, rows: Sequence[EdgeRow], hidden: bool) -> CapacityPeriod:
    if hidden and period != IN_SAMPLE:
        return CapacityPeriod(period, OOS_HIDDEN, None, None, None, None)
    row = next((r for r in rows if STORED_PERIOD.get(r.slice_kind) == period), None)
    if row is None or not row.pick_adv_known:  # none stored, or no pick had a volume
        return CapacityPeriod(period, NOT_STORED, None, None, None, None)
    return CapacityPeriod(
        period, MEASURED, row.picks, row.pick_adv_median, row.pick_adv_known, row.pick_adv_low
    )


def capacity_of(basis: BasisRows, floor_usd: float) -> EdgeCapacity:
    """The capacity of ``basis``; ``floor_usd``: the site's floor as configured now."""
    periods = tuple(_period(p, basis.rows, basis.hidden) for p in PERIODS)
    state = MEASURED if any(p.state == MEASURED for p in periods) else NOT_STORED
    return EdgeCapacity(state, basis.variant, basis.horizon, floor_usd, periods)


def load_edge_capacity(
    ctx: Stores, edge: Edge, variant: str | None = None, horizon: int | None = None
) -> EdgeCapacity:
    """The capacity of ``edge``'s official result at the verdict's basis (or the screen and
    holding period named), against the site's floor."""
    floor = load_verdict(ctx.configs).capacity_adv_floor_usd
    return capacity_of(load_basis_rows(ctx, edge, variant, horizon), floor)
