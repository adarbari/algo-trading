"""``ReviewList``: rows the owner curates (listings marked for FIGI review, ETFs whose leverage
the rules could not classify)."""

import datetime as dt
from typing import Self

import strawberry
from strawberry.scalars import JSON

from algotrade.services.read.ops import review


@strawberry.type(
    description="Rows to review: `session` the snapshot or run they come from (null: nothing "
    "stored), `source` a run id or the reference table, `items` one row each"
)
class ReviewList:
    session: dt.date | None
    source: str
    items: list[JSON]

    @classmethod
    def of(cls, d: review.ReviewList) -> Self:
        return cls(session=d.session, source=d.source, items=[JSON(i) for i in d.items])
