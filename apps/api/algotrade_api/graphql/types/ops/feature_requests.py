"""``FeatureRequestList``: the missing features traders asked for, ranked, for the Admin "Feature
requests" page (ADR 0066 amendment 2026-10-11). Counts only: no user id and no span is a field."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.ops import feature_requests


@strawberry.type(
    description="One requested feature in the ranking, best first (`rank` is 1-based; promoted "
    "and won't-do ones come after every open one). `ref` is the backlog key, or the slug of a "
    "request not yet mapped (`unmapped`, status UNMAPPED); `users` the distinct askers and "
    "`timesAsked` the distinct (user, day) asks, never who. `status` is OPEN, PROMOTED, WONT_DO "
    "or UNMAPPED; `promotedTo` the site feature a promoted one became"
)
class FeatureRequestRow:
    rank: int
    ref: str
    description: str
    feasibility: str
    score: float
    users: int
    times_asked: int
    first_seen: dt.date | None
    last_seen: dt.date
    status: str
    promoted_to: str
    unmapped: bool

    @classmethod
    def of(cls, d: feature_requests.FeatureRequestRow) -> Self:
        return cls(
            rank=d.rank,
            ref=d.ref,
            description=d.description,
            feasibility=d.feasibility,
            score=d.score,
            users=d.users,
            times_asked=d.times_asked,
            first_seen=d.first_seen,
            last_seen=d.last_seen,
            status=d.status,
            promoted_to=d.promoted_to,
            unmapped=d.unmapped,
        )


@strawberry.type(
    description="The ranked feature requests of the last `days` days up to `today` (exchange "
    "date): a date range, not one session. Admin only; counts, never a user or a span"
)
class FeatureRequestList:
    today: dt.date
    days: int
    rows: list[FeatureRequestRow]

    @classmethod
    def of(cls, d: feature_requests.FeatureRequestList) -> Self:
        return cls(today=d.today, days=d.days, rows=[FeatureRequestRow.of(r) for r in d.rows])
