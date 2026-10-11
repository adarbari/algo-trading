"""``EdgeHorizons`` (ADR 0064, "where it worked"): the verdict's screen at every holding period the
run measured, one row per horizon with its in-sample, out-of-sample and whole-history figures,
the basis's own row marked, and ``oos_by``: the date the horizon's out-of-sample count is
expected to reach the verdict's bar (``min_oos_trades``), read off the stored projection of the
horizon's own ``all`` row exactly as the verdict's outlook reads the basis's (``evidence.project``;
an estimate, never an input to a verdict). A period not stored is ``not_stored``; a hidden
copy's out-of-sample and whole-history periods are ``oos_hidden``. The basis is the verdict's own
(``edge_evidence.basis``), never re-chosen."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from algotrade.config.site.settings import load_verdict
from algotrade.services.read.context import Stores
from algotrade.services.read.edge_evidence.basis import OfficialBasis
from algotrade.services.read.edge_evidence.costs import (
    MEASURED,
    NOT_STORED,
    OOS_HIDDEN,
    OUT_OF_SAMPLE,
    STORED_PERIOD,
)
from algotrade.services.read.edge_evidence.slices.figures import SliceFigure, figures_of
from algotrade.services.read.evaluation import evidence, runs
from algotrade.services.read.evaluation.edges import Edge
from algotrade.services.read.evaluation.evidence import UNPROJECTABLE
from algotrade.services.read.evaluation.runs import EdgeRow
from algotrade.services.read.evaluation.verdict import projection_of

REACHED = "reached"
OOS_BY_STATES = (*evidence.PROJECTION_STATES, REACHED)


@dataclass(frozen=True)
class OosBy:
    """When a horizon's out-of-sample count reaches the ``needed`` trades: ``state`` as the
    verdict's outlook (projected, not_stored, beyond_projection, unprojectable, oos_hidden) or
    ``reached`` (``have`` is enough); ``remaining`` still to come and, when projected,
    ``expected_by`` (the exit of the trade that completes the count) at ``fill_ratio`` of the
    decision sessions measured."""

    state: str
    needed: int
    have: int | None
    remaining: int | None
    expected_by: date | None
    fill_ratio: float | None


@dataclass(frozen=True)
class HorizonRow:
    """One holding period of ``horizon`` sessions: ``basis`` it is the verdict's, its figures by
    period and ``oos_by``."""

    horizon: int
    basis: bool
    figures: tuple[SliceFigure, ...]
    oos_by: OosBy


@dataclass(frozen=True)
class EdgeHorizons:
    """The basis screen ``variant`` at each holding period (shortest first): ``state`` measured
    (rows) or not_stored; ``needed`` the verdict's out-of-sample trades."""

    state: str
    variant: str | None
    needed: int
    rows: tuple[HorizonRow, ...]


def _oos_by(found: tuple[EdgeRow, ...], hidden: bool, schedule: str, needed: int) -> OosBy:
    oos = next((r for r in found if STORED_PERIOD.get(r.slice_kind) == OUT_OF_SAMPLE), None)
    whole = next((r for r in found if r.slice_kind == "all"), None)
    if hidden:
        return OosBy(OOS_HIDDEN, needed, None, None, None, None)
    if oos is None:
        return OosBy(NOT_STORED, needed, None, None, None, None)
    have = oos.sessions or 0
    remaining = max(needed - have, 0)
    if remaining == 0:
        return OosBy(REACHED, needed, have, 0, None, None)
    if schedule.startswith("on_event:"):
        return OosBy(UNPROJECTABLE, needed, have, remaining, None, None)
    state, by, ratio = evidence.project(remaining, projection_of(whole) if whole else None)
    return OosBy(state, needed, have, remaining, by, ratio)


def horizons_of(
    basis: OfficialBasis, served: tuple[EdgeRow, ...], schedule: str, needed: int
) -> EdgeHorizons:
    """The holding periods of ``basis``'s screen among ``served`` (the official run's rows)."""
    if basis.key is None:
        return EdgeHorizons(NOT_STORED, None, needed, ())
    variant, own = basis.key
    by_horizon: dict[int, list[EdgeRow]] = defaultdict(list)
    for r in served:
        if r.edge_variant == runs.MAIN and r.role != runs.BASELINE and r.variant == variant:
            by_horizon[r.horizon_sessions].append(r)
    rows = tuple(
        HorizonRow(
            h,
            h == own,
            figures_of(tuple(found), basis.hidden, needed),
            _oos_by(tuple(found), basis.hidden, schedule, needed),
        )
        for h, found in sorted(by_horizon.items())
    )
    return EdgeHorizons(MEASURED if rows else NOT_STORED, variant, needed, rows)


def load_horizons(ctx: Stores, edge: Edge, basis: OfficialBasis) -> EdgeHorizons:
    """The holding periods of ``edge``'s official result at the verdict's screen."""
    served = runs.load_run_rows(ctx, basis.run) if basis.run is not None else ()
    return horizons_of(basis, served, edge.schedule, load_verdict(ctx.configs).min_oos_trades)
