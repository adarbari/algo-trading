"""``Session``: the one session every value of a response is for (ADR 0036), and what is
stored for it (``missing``: the expected session-grain tables with no partition for it)."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read import session


@strawberry.type(
    description="The session a read serves: every value in the response is for `date` "
    "(ADR 0036). `missing` lists the nightly tables with no partition for it; identity is "
    "read from the reference snapshot `referenceSnapshot` (`preSnapshot`: one taken later)."
)
class Session:
    date: dt.date
    requested: dt.date | None
    is_latest: bool
    latest_with_bars: dt.date | None
    reference_snapshot: dt.date | None
    pre_snapshot: bool
    present: list[str]
    missing: list[str]

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
        )
