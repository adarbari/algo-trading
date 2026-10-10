"""``Session``: the one session every value of a response is for (ADR 0036), and what is
stored for it (``unavailable``: what the expected session-grain tables with no partition for
it leave out, by feature and in public words: ADR 0056)."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read import session
from algotrade.services.read.availability.cause import UnavailableKind
from algotrade_api.graphql.types.availability import Unavailable

strawberry.enum(session.NewerState, description="What a session newer than the one served is doing")


@strawberry.type(
    description="The newest session after the one served whose nightly workflow is not "
    "complete (ADR 0062): its `date`, its `state`, and for a failure the public `kind` only "
    "(never the step or its cause: ADR 0056)"
)
class NewerSession:
    date: dt.date
    state: session.NewerState
    kind: UnavailableKind | None

    @classmethod
    def of(cls, d: session.NewerSession) -> Self:
        return cls(date=d.date, state=d.state, kind=d.kind)


@strawberry.type(
    description="The session a read serves: every value in the response is for `date` "
    "(ADR 0036). `unavailable` says what the nightly tables with no partition for it leave "
    "out; identity is read from the reference snapshot `referenceSnapshot` (`preSnapshot`: "
    "one taken later). A read with no date serves the latest session whose nightly workflow "
    "is complete (ADR 0062): `newer` is the later session still processing or failing "
    "(null: none, or a date was asked for), `complete` whether `date`'s workflow is complete "
    "(false on a store with none complete yet: the latest bars are served unconfirmed)."
)
class Session:
    date: dt.date
    requested: dt.date | None
    is_latest: bool
    latest_with_bars: dt.date | None
    reference_snapshot: dt.date | None
    pre_snapshot: bool
    unavailable: list[Unavailable]
    complete: bool
    newer: NewerSession | None

    @classmethod
    def of(cls, d: session.Session) -> Self:
        return cls(
            date=d.date,
            requested=d.requested,
            is_latest=d.is_latest,
            latest_with_bars=d.latest_with_bars,
            reference_snapshot=d.reference_snapshot,
            pre_snapshot=d.pre_snapshot,
            unavailable=[Unavailable.of(u) for u in d.unavailable],
            complete=d.complete,
            newer=NewerSession.of(d.newer) if d.newer else None,
        )
