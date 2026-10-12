"""``MyFeatureRequest``: one feature the viewer's own Describe-it drafts listed as missing (ADR 0066
amendment), their own history only: never a count or a trace of another user."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.ops import feature_requests


@strawberry.type(
    description="A feature the viewer asked for: `ref` the backlog key (an alias counts under its "
    "key) or the slug of a request not yet mapped (`unmapped`); `status` the backlog's; "
    "`firstAsked` / `lastAsked` the days it was asked and `timesAsked` how many distinct days; "
    "`span` the piece of the viewer's own sentence of the latest ask (null: not stored); "
    "`feasibility` the backlog item's, else the latest ask's; "
    "`askedBeforeToday` whether an ask falls on an earlier exchange date than today"
)
class MyFeatureRequest:
    ref: str
    description: str
    status: str
    unmapped: bool
    first_asked: dt.date
    last_asked: dt.date
    times_asked: int
    promoted_to: str
    feasibility: str
    span: str | None
    asked_before_today: bool

    @classmethod
    def of(cls, d: feature_requests.MyRequest) -> Self:
        return cls(
            ref=d.ref,
            description=d.description,
            status=d.status,
            unmapped=d.unmapped,
            first_asked=d.first_asked,
            last_asked=d.last_asked,
            times_asked=d.times_asked,
            promoted_to=d.promoted_to,
            feasibility=d.feasibility,
            span=d.span,
            asked_before_today=d.asked_before_today,
        )
