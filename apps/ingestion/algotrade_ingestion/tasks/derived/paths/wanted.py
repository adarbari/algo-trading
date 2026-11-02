"""The positions a path writer stores (ADR 0088, design 2.5; E3c-2): every position of the site's
open edge documents (their outcome, each ``[[variants]]``' and each case point of a case-valued
parameter, for each hold of its ``horizon_sessions``), by stored key. ``OPTION``: the
``option_pnl`` positions (option-outcomes); ``SHARES``: the share positions of a return outcome
that declare an ``[outcome.exit]`` (share-outcomes; one without keeps its fixed-horizon outcome).
A new edge needs no code change; two setups that resolve to one key (and, for shares, one
benchmark) share its rows."""

from collections.abc import Collection
from dataclasses import dataclass

from algotrade.config.edges.document import CLOSED, Edge, Outcome
from algotrade.config.edges.positions.chain import CHAIN_KIND
from algotrade.config.edges.positions.key import case_points, position_key, share_position_key
from algotrade.config.edges.positions.spec import ExitRule, exit_rules, share_exit_rules
from algotrade.config.edges.positions.templates import (
    OPTION,
    RETURN_KINDS,
    SHARES,
    SIDE_TEMPLATES,
    Templates,
)
from algotrade.core.model.fields import is_position_field


@dataclass(frozen=True)
class Wanted:
    """One position to write for a window ending at a night: the outcome (a document's, a
    variant's or a case point's) held at most ``hold`` sessions, its stored ``key``, its ordered
    exit ``rules`` and the catalogue ``fields`` they name; a share position also its outcome's
    ``benchmark`` ticker (``none``: no excess), stored beside the key (two setups of one position
    and two benchmarks are two row sets)."""

    outcome: Outcome
    hold: int
    key: str
    rules: tuple[ExitRule, ...]
    fields: tuple[str, ...]
    benchmark: str | None = None


def _stored(outcome: Outcome, kind: str) -> bool:
    if outcome.position is None:
        return False
    if kind == OPTION:
        return outcome.kind == CHAIN_KIND
    share = outcome.kind in RETURN_KINDS and outcome.side in SIDE_TEMPLATES
    return share and outcome.position.exit is not None and outcome.side != "long_short"


def positions_wanted(
    edges: Collection[Edge], templates: Templates, kind: str = OPTION
) -> list[Wanted]:
    """The ``kind`` positions (``OPTION`` or ``SHARES``) of the open edge documents, one per key,
    ordered by hold then key."""
    outcomes = [
        o
        for e in edges
        if e.status not in CLOSED
        for o in (e.outcome, *(v.outcome for v in e.variants))
    ]
    found: dict[tuple[str, str | None], Wanted] = {}
    for outcome in (o for o in outcomes if _stored(o, kind)):
        for point in case_points(outcome, templates):
            exit = point.position.exit if point.position else None
            rules = exit_rules(exit) if kind == OPTION else share_exit_rules(exit, point.side)
            names = {
                r.field for x in rules for r in x.rule.rules() if not is_position_field(r.field)
            }
            for hold in point.horizon_sessions:
                if kind == OPTION:
                    key, benchmark = position_key(point, hold), None
                else:
                    key, benchmark = share_position_key(point, hold), point.benchmark
                found[key, benchmark] = Wanted(
                    point, hold, key, rules, tuple(sorted(names)), benchmark
                )
    return sorted(found.values(), key=lambda w: (w.hold, w.key, w.benchmark or ""))


__all__ = ["OPTION", "SHARES", "Wanted", "positions_wanted"]
