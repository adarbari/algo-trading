"""``Unavailable`` for stored tables with nothing for the session (ADR 0056): the one place a
list of table names becomes the public object (a kind, the catalogue features the table feeds,
a Guide term) with the table as the leaf of its admin-only cause. A page never serves the
table names themselves."""

from collections.abc import Iterable
from datetime import date

from algotrade.core.model.fields import group_of_table
from algotrade.features.registry import GROUPS
from algotrade.services.read.availability.cause import (
    Cause,
    CauseLevel,
    CauseLink,
    Unavailable,
    UnavailableKind,
    table_cause,
)

__all__ = ["features_of", "unavailable_tables"]


def features_of(table: str) -> tuple[str, ...]:
    """The catalogue fields stored in ``table`` (none: it is not a feature group's table)."""
    found = group_of_table(table)
    group = GROUPS.get(found[1]) if found is not None else None
    return tuple(f.name for f in group.features) if group is not None else ()


def unavailable_tables(
    tables: Iterable[str],
    session: date,
    status: str = "NO_PARTITION",
    kind: UnavailableKind = UnavailableKind.SYSTEM,
) -> tuple[Unavailable, ...]:
    """One ``Unavailable`` per table (sorted) that has nothing for ``session``: the features
    it hides and, as its cause, the table then the features it leaves unavailable."""
    return tuple(_one(table, session, status, kind) for table in sorted(set(tables)))


def _one(table: str, session: date, status: str, kind: UnavailableKind) -> Unavailable:
    names = features_of(table)
    leaf = table_cause(table, f"{table} has no rows for {session.isoformat()}", status, session)
    if not names:
        return Unavailable(kind, names, leaf)
    message = f"features {', '.join(names)} unavailable"
    end = CauseLink(CauseLevel.FEATURE, ", ".join(names), "UNAVAILABLE", message, None, session)
    return Unavailable(kind, names, Cause((*leaf.links, end)))
