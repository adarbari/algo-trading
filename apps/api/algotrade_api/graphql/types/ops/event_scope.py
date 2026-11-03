"""``EventScope`` (ADR 0050, plan 5.5): the event-study scope list for the Admin screen: each
listed name with its reasons and source, last deep-dive review (stale after 90 days), the share of
its biggest moves that are attributed, the admin's removals and the macro calendar's reach.
Admin only (the field is ``AdminOnly``)."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.event_scope import big_moves, event_scope
from algotrade_api.graphql.types.instruments.feature import Unknown


@strawberry.type(
    description="Of a name's `big` largest moves of the last year, how many have an attribution "
    "known by the session (any source); `share` is `attributed / big`"
)
class MoveShare:
    big: int
    attributed: int
    share: float

    @classmethod
    def of(cls, d: big_moves.MoveShare) -> Self:
        return cls(big=d.big, attributed=d.attributed, share=d.share)


@strawberry.type(
    description="A name of the scope list: `reasons` why it is in scope (tier, list, requested, "
    "reference), `source` where its list entry came from (site: the reviewed file; admin: "
    "added by `by` at `at`, null for a site name), `addedOn` and `note` of that entry, "
    "`lastReview` the date of the owner's last deep-dive dossier known by the session (null: "
    "none), `stale` no review in `staleDays` days or never, `moves` the share of its largest "
    "moves attributed (null: unknown, e.g. under a year of bars)"
)
class ScopeName:
    instrument_id: str
    symbol: str
    reasons: list[str]
    source: str
    added_on: dt.date
    note: str
    by: str | None
    at: dt.datetime | None
    last_review: dt.date | None
    stale: bool
    moves: MoveShare | None

    @classmethod
    def of(cls, d: event_scope.ScopeName) -> Self:
        return cls(
            instrument_id=d.instrument_id,
            symbol=d.symbol,
            reasons=list(d.reasons),
            source=d.source,
            added_on=d.added_on,
            note=d.note,
            by=d.by,
            at=d.at,
            last_review=d.last_review,
            stale=d.stale,
            moves=MoveShare.of(d.moves) if d.moves is not None else None,
        )


@strawberry.type(
    description="A site-list name the admin removed (the site file is unchanged): by whom and "
    "when, and the reasons it is still in scope (empty: not any more); restoring it is an add"
)
class RemovedName:
    symbol: str
    by: str
    at: dt.datetime
    note: str
    reasons: list[str]

    @classmethod
    def of(cls, d: event_scope.RemovedName) -> Self:
        return cls(symbol=d.symbol, by=d.by, at=d.at, note=d.note, reasons=list(d.reasons))


@strawberry.type(
    description="The event-study scope list as of the session (the site file plus the admin's "
    "additions minus removals): `names` in list order, `staleCount` how many of them are stale, "
    "the admin's `removed`, the `unresolved` "
    "symbols the session's reference snapshot does not know, `otherNames` how many more names "
    "are in scope by a put tier or as a fund's reference, and the macro calendar's reach: "
    "`macroReleases` scheduled in the next `macroDays` days (null with `macroUnknown`: the "
    "calendar has nothing known by the session)"
)
class EventScope:
    session: dt.date
    stale_days: int
    stale_count: int
    names: list[ScopeName]
    removed: list[RemovedName]
    unresolved: list[str]
    other_names: int
    macro_days: int
    macro_releases: int | None
    macro_unknown: Unknown | None

    @classmethod
    def of(cls, d: event_scope.EventScope) -> Self:
        return cls(
            session=d.session,
            stale_days=d.stale_days,
            stale_count=d.stale_count,
            names=[ScopeName.of(r) for r in d.names],
            removed=[RemovedName.of(r) for r in d.removed],
            unresolved=list(d.unresolved),
            other_names=d.other_names,
            macro_days=d.macro_days,
            macro_releases=d.macro_releases,
            macro_unknown=Unknown.of(d.macro_unknown) if d.macro_unknown is not None else None,
        )
