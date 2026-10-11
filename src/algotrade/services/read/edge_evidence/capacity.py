"""How much money an edge's picks can take (``EdgeCapacity``, ADR 0064 decision 5): per period,
the median 20-day dollar volume of the picks the harness counted, how many have one stored and
how many trade below the site's floor (``capacity_adv_floor_usd``, ``verdict.toml``). Pure over
the stored ``pick_adv_*`` columns; the floor is applied when the harness computes the
statistics, so a run from before a changed floor still says which floor it used only in its own
count. A period is ``measured``, ``not_stored`` (an older run, no split, or no pick had a stored
volume) or ``oos_hidden`` (a copy's out-of-sample result is withheld). ``position_share`` is what
a position of the site's ``capacity_position_usd`` is of the median pick's volume (served, never
stored); the site floor binds only when it is above the floor the edge's own universe already
requires (``universe_floor_usd``), otherwise no pick can be below it by construction."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from algotrade.config.site.settings import load_verdict
from algotrade.config.strategy.schema import Selection, parse_selection
from algotrade.core.model.predicates import Group, Rule
from algotrade.services.read.context import Stores
from algotrade.services.read.edge_evidence.basis import OfficialBasis, official_basis
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
ADV_FIELD: Final = "rollup.price_stats@v2.adv_usd_20d"  # the 20-day dollar volume a floor reads
FLOOR_OPS: Final = ("gt", "gte")


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
    position_share: float | None = None  # the site's position over the median pick's volume


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
    position_usd: float = 0.0
    universe_floor_usd: float | None = None  # the floor the edge's universe selection already has
    floor_binds: bool = True  # the site floor is above it (or the universe's is not known)


def _period(
    period: str, rows: Sequence[EdgeRow], hidden: bool, position_usd: float
) -> CapacityPeriod:
    if hidden and period != IN_SAMPLE:
        return CapacityPeriod(period, OOS_HIDDEN, None, None, None, None)
    row = next((r for r in rows if STORED_PERIOD.get(r.slice_kind) == period), None)
    if row is None or not row.pick_adv_known:  # none stored, or no pick had a volume
        return CapacityPeriod(period, NOT_STORED, None, None, None, None)
    share = position_usd / row.pick_adv_median if row.pick_adv_median else None  # never /0
    return CapacityPeriod(
        period,
        MEASURED,
        row.picks,
        row.pick_adv_median,
        row.pick_adv_known,
        row.pick_adv_low,
        share,
    )


def capacity_of(
    basis: BasisRows,
    floor_usd: float,
    position_usd: float,
    universe_floor_usd: float | None = None,
) -> EdgeCapacity:
    """The capacity of ``basis``; ``floor_usd``: the site's floor as configured now,
    ``position_usd`` the position sized against the median pick's volume and
    ``universe_floor_usd`` the floor the edge's universe already requires (None: it has none we
    can read, so the site floor is shown)."""
    periods = tuple(_period(p, basis.rows, basis.hidden, position_usd) for p in PERIODS)
    state = MEASURED if any(p.state == MEASURED for p in periods) else NOT_STORED
    binds = universe_floor_usd is None or floor_usd > universe_floor_usd
    return EdgeCapacity(
        state, basis.variant, basis.horizon, floor_usd, periods, position_usd,
        universe_floor_usd, binds,
    )  # fmt: skip


def _floors(group: Group) -> list[float]:
    """The dollar-volume floors a selection's ``all`` rules require (nested ``all`` groups too;
    an ``any`` or ``not`` group is no floor)."""
    found: list[float] = []
    for child in group.children:
        if isinstance(child, Rule):
            ok = child.field == ADV_FIELD and child.op in FLOOR_OPS
            if ok and isinstance(child.value, (int, float)) and not isinstance(child.value, bool):
                found.append(float(child.value))
        elif child.kind == "all":
            found.extend(_floors(child))
    return found


def universe_floor(ctx: Stores, edge: Edge, owner: str) -> float | None:
    """The 20-day dollar-volume floor of ``edge``'s universe selection (a named preset; None:
    an inline selection, none, or no such floor), read from the scope of the run's ``owner`` then
    the site, as the harness resolved it."""
    name = edge.settings.universe if edge.settings else ""
    if not name:
        return None
    for scope in (owner, "site"):
        doc = ctx.configs.load(scope, "selections", name)
        if doc is not None:
            selection: Selection = parse_selection(doc, f"{scope}/selections/{name}")
            floors = _floors(selection.where) if selection.where.kind == "all" else []
            return max(floors) if floors else None
    return None


def load_edge_capacity(ctx: Stores, edge: Edge, basis: OfficialBasis | None = None) -> EdgeCapacity:
    """The capacity of ``edge``'s official result at the verdict's basis (``basis``: the
    one the page resolved; resolved here when not given), against the site's floor."""
    settings = load_verdict(ctx.configs)
    basis = basis or official_basis(ctx, edge)
    owner = basis.run.owner if basis.run is not None else ctx.user.user_id
    return capacity_of(
        load_basis_rows(ctx, basis),
        settings.capacity_adv_floor_usd,
        settings.capacity_position_usd,
        universe_floor(ctx, edge, owner),
    )
