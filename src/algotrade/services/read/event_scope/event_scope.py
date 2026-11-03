"""``EventScope`` (EV8, ADR 0050 plan 5.5): the names of the event-study scope list for the
Admin screen, as of the session. The list is the effective one (``config.site.events.scope``:
the site file plus the admin's additions minus removals); every symbol becomes an id only through
the session's reference snapshot (ADR 0018, ``services.events.scope``), the ones it does not know
are returned as ``unresolved``.

Per listed name: why it is in scope (all reasons: a name removed from the list still in a put tier
shows as ``removed`` with its remaining reasons), where its list entry came from (``site`` or
``admin``, with who and when for the admin's), the owner's last deep-dive review as of the session
(``data.dossier``: None when none was imported by then) and ``stale`` when that is over
``STALE_DAYS`` days ago or never; and the share of its ``TOP_MOVES`` biggest moves of the last year
that are attributed (``big_moves``; None when unknown). The macro calendar's next ``MACRO_DAYS``
days count (``ahead.macro_releases``) is there so a missing release is noticed; None with its
UNKNOWN when the calendar has nothing known by the session. Names in scope only by their put tier
or as a fund's reference are counted (``other_names``), not listed: the admin changes the list.

An admin read (the field is ``AdminOnly``); nothing here is role-filtered further."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from algotrade.config.site.events.scope import AdminChange, effective_list
from algotrade.data.dossier.reading import dossiers_as_of
from algotrade.services.events.scope import LIST, scoped_instruments
from algotrade.services.read.context import ReadContext
from algotrade.services.read.event_scope.big_moves import MoveShare, attributed_moves
from algotrade.services.read.events.ahead import macro_releases
from algotrade.services.read.values import Unknown

STALE_DAYS = 90  # a name not reviewed in this many days is flagged (plan 4.6)
MACRO_DAYS = 90  # the macro calendar's reach the Admin screen shows


@dataclass(frozen=True)
class ScopeName:
    """A listed name: ``reasons`` (tier, list, requested, reference), ``source`` of its list entry
    (site | admin; ``by`` / ``at`` the admin's), ``last_review`` the dossier's review date
    (None: never imported by the session), ``stale``, ``moves`` (None: unknown)."""

    instrument_id: str
    symbol: str
    reasons: tuple[str, ...]
    source: str
    added_on: date
    note: str
    by: str | None
    at: datetime | None
    last_review: date | None
    stale: bool
    moves: MoveShare | None


@dataclass(frozen=True)
class RemovedName:
    """A site name the admin took off the list (``reasons``: why it is still in scope, if it is)."""

    symbol: str
    by: str
    at: datetime
    note: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class EventScope:
    """The scope list as of ``session``: ``names`` in list order, the admin's ``removed`` names,
    the ``unresolved`` symbols, how many other names are in scope by tier or reference
    (``other_names``), the macro releases scheduled in the next ``macro_days`` days (None with
    ``macro_unknown``: none known) and the staleness limit."""

    session: date
    stale_days: int
    names: tuple[ScopeName, ...]
    removed: tuple[RemovedName, ...]
    unresolved: tuple[str, ...]
    other_names: int
    macro_days: int
    macro_releases: int | None
    macro_unknown: Unknown | None


def _removed(change: AdminChange, reasons: tuple[str, ...]) -> RemovedName:
    return RemovedName(change.symbol, change.by, change.at, change.note, reasons)


def load_event_scope(ctx: ReadContext) -> EventScope:
    """The effective scope list of the session with its review dates, attributed shares and the
    macro calendar's reach."""
    day = ctx.session.date
    listed = effective_list(ctx.configs)
    scope = scoped_instruments(ctx.reader, ctx.configs, day)
    by_symbol = {n.symbol: n for n in scope.names}
    named = {n.symbol: by_symbol[n.symbol] for n in listed.names if n.symbol in by_symbol}
    dossiers = dossiers_as_of(ctx.reader, day, [n.instrument_id for n in named.values()]).dossiers
    moves = attributed_moves(ctx.reader, day, [n.instrument_id for n in named.values()])
    rows = []
    for entry in listed.names:
        found = named.get(entry.symbol)
        if found is None:
            continue
        dossier = dossiers.get(found.instrument_id)
        reviewed = dossier.reviewed_on if dossier is not None else None
        rows.append(
            ScopeName(
                found.instrument_id,
                found.symbol,
                found.reasons,
                entry.source,
                entry.added_on,
                entry.note,
                entry.by,
                entry.at,
                reviewed,
                reviewed is None or day - reviewed > timedelta(days=STALE_DAYS),
                moves.get(found.instrument_id),
            )
        )
    gone = tuple(
        _removed(c, by_symbol[c.symbol].reasons if c.symbol in by_symbol else ())
        for c in listed.removed
    )
    macro, macro_gap = macro_releases(ctx, day + timedelta(days=MACRO_DAYS))
    return EventScope(
        session=day,
        stale_days=STALE_DAYS,
        names=tuple(rows),
        removed=gone,
        unresolved=scope.unresolved,
        other_names=sum(1 for n in scope.names if LIST not in n.reasons),
        macro_days=MACRO_DAYS,
        macro_releases=None if macro_gap is not None else len(macro),
        macro_unknown=macro_gap,
    )
