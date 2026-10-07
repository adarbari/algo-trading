"""``EventCalendar`` (ADR 0050): the events ahead of a set of names, one entry per day, for the
cross-name Calendar page: the names' own events on their rows, the market-wide ones once."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.events import event_calendar
from algotrade_api.graphql.types.events.instrument_events import AheadEvent, EventGap


@strawberry.type(description="A name on the calendar: its id and ticker in the session's snapshot")
class CalendarName:
    instrument_id: str
    symbol: str

    @classmethod
    def of(cls, d: event_calendar.CalendarName) -> Self:
        return cls(instrument_id=d.instrument_id, symbol=d.symbol)


@strawberry.type(
    description="An event on a day: the name whose row it is on (null: market-wide, a macro "
    "release or a market-structure day) and the event; a fund's reference earnings are on the "
    "fund's row, `event.subjectId` the stock"
)
class CalendarEvent:
    instrument_id: str | None
    symbol: str | None
    event: AheadEvent

    @classmethod
    def of(cls, d: event_calendar.CalendarEvent) -> Self:
        return cls(instrument_id=d.instrument_id, symbol=d.symbol, event=AheadEvent.of(d.event))


@strawberry.type(
    description="A day of the window (every session, and a closed day only when an event "
    "falls on it) and its events: the names' first, in name order, then the market-wide ones"
)
class CalendarDay:
    date: dt.date
    is_session: bool
    events: list[CalendarEvent]

    @classmethod
    def of(cls, d: event_calendar.CalendarDay) -> Self:
        return cls(
            date=d.date, is_session=d.is_session, events=[CalendarEvent.of(e) for e in d.events]
        )


@strawberry.type(
    description="The calendar of `names` from the session through `end`: the days in order, "
    "the parts not known for the session (`gaps`), the asked ids the reference snapshot lacks "
    "(`missing`) and the scope list's symbols it does not know (`unresolved`)"
)
class EventCalendar:
    session: dt.date
    end: dt.date
    names: list[CalendarName]
    days: list[CalendarDay]
    gaps: list[EventGap]
    missing: list[str]
    unresolved: list[str]

    @classmethod
    def of(cls, d: event_calendar.EventCalendar) -> Self:
        return cls(
            session=d.session,
            end=d.end,
            names=[CalendarName.of(n) for n in d.names],
            days=[CalendarDay.of(day) for day in d.days],
            gaps=[EventGap.of(g) for g in d.gaps],
            missing=list(d.missing),
            unresolved=list(d.unresolved),
        )
