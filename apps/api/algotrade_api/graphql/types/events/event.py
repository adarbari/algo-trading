"""``Event``: one stored event of an instrument (an ``events/*`` row: earnings, dividend,
split, reference change), read by its event date (ADR 0007), for the events list and chart
markers. Earnings dates as facts are catalogue features, never read from these."""

import datetime as dt
from typing import Self

import strawberry
from strawberry.scalars import JSON

from algotrade.services.read.events import stored as events


@strawberry.type(
    description="A stored event: `table` events/<kind>, `date` the event date (UTC), "
    "`values` the row's other columns, `sourceUrl` the page the row came from (a report stored "
    "from an 8-K: its sec.gov filing index; null when there is none), `confirmed` a report "
    "stored from the company's own 8-K results release, which beats the exchange calendar's "
    "row of the same report"
)
class Event:
    instrument_id: str
    table: str
    kind: str
    date: dt.date
    ts: dt.datetime
    values: JSON
    source_url: str | None
    confirmed: bool

    @classmethod
    def of(cls, d: events.Event) -> Self:
        return cls(
            instrument_id=d.instrument_id,
            table=d.table,
            kind=d.kind,
            date=d.date,
            ts=d.ts,
            values=JSON(d.values),
            source_url=d.source_url,
            confirmed=d.confirmed,
        )
