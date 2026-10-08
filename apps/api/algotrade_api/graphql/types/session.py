"""``Session``: the one session every value of a response is for (ADR 0036), and what is
stored for it (``unavailable``: what the expected session-grain tables with no partition for
it leave out, by feature and in public words; ``present`` / ``missing`` are the legacy table
lists, served to admins only: ADR 0056)."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read import session
from algotrade_api.graphql.permissions import AdminCause
from algotrade_api.graphql.types.availability import Unavailable


@strawberry.type(
    description="The session a read serves: every value in the response is for `date` "
    "(ADR 0036). `unavailable` says what the nightly tables with no partition for it leave "
    "out; `present` / `missing` list those tables (legacy, admins only: empty for anyone "
    "else); identity is read from the reference snapshot `referenceSnapshot` (`preSnapshot`: "
    "one taken later)."
)
class Session:
    date: dt.date
    requested: dt.date | None
    is_latest: bool
    latest_with_bars: dt.date | None
    reference_snapshot: dt.date | None
    pre_snapshot: bool
    present: list[str] = strawberry.field(extensions=[AdminCause([])])
    missing: list[str] = strawberry.field(extensions=[AdminCause([])])
    unavailable: list[Unavailable]

    @classmethod
    def of(cls, d: session.Session) -> Self:
        return cls(
            date=d.date,
            requested=d.requested,
            is_latest=d.is_latest,
            latest_with_bars=d.latest_with_bars,
            reference_snapshot=d.reference_snapshot,
            pre_snapshot=d.pre_snapshot,
            present=list(d.present),
            missing=list(d.missing),
            unavailable=[Unavailable.of(u) for u in d.unavailable],
        )
