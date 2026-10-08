"""``EventCalendar`` (ADR 0050, plan 5.3): the events ahead of a set of names over the next
``days`` calendar days, one entry per day, for the cross-name Calendar page. The names come
from the caller (a screen's results, an explicit list) and, with ``scope``, the site list
``config/site/events/scope.toml`` (resolved by the one scope owner, ``services.events``,
through the session's reference snapshot; unknown symbols returned, never dropped).

Each day lists the names' own events (own and reference earnings, with the name they belong
to) and the market-wide ones once (macro releases, market-structure days: ``instrument_id``
None). Every session of the window is a day, even an empty one; a non-session day appears
only when an event falls on it. Same point-in-time rules and gaps as ``InstrumentEvents``
(``ahead.load_ahead``)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from algotrade.core.time.calendar import is_session, sessions_between
from algotrade.services.events.scope import LIST, scoped_instruments
from algotrade.services.read.context import ReadContext
from algotrade.services.read.events.ahead import OWN_EARNINGS, AheadEvent, EventGap, load_ahead
from algotrade.services.read.instruments.identity import load_instruments


@dataclass(frozen=True)
class CalendarName:
    """A name on the calendar: its id and its ticker in the session's reference snapshot."""

    instrument_id: str
    symbol: str


@dataclass(frozen=True)
class CalendarEvent:
    """An event on a day: the name it is on the calendar for (None: market-wide) and the
    event (a fund's reference earnings: on the fund's row, ``event.subject_id`` the stock)."""

    instrument_id: str | None
    symbol: str | None
    event: AheadEvent


@dataclass(frozen=True)
class CalendarDay:
    """One day of the window and its events (names' events first, by name order)."""

    date: date
    is_session: bool
    events: tuple[CalendarEvent, ...]


@dataclass(frozen=True)
class EventCalendar:
    """The calendar of ``names`` from the session through ``end``: ``days`` in order, the
    parts not known for the session (``gaps``), the asked ids the reference snapshot lacks
    (``missing``) and the scope list's symbols it does not know (``unresolved``)."""

    session: date
    end: date
    names: tuple[CalendarName, ...]
    days: tuple[CalendarDay, ...]
    gaps: tuple[EventGap, ...]
    missing: tuple[str, ...]
    unresolved: tuple[str, ...]


def _fund_own(gap: EventGap, funds: set[str]) -> bool:
    """A fund's own-earnings gap: an ETF never reports, so the calendar banner skips it (the
    instrument page keeps it, its reference earnings being the fund's exposure)."""
    return gap.part == OWN_EARNINGS and gap.instrument_id in funds


def load_event_calendar(
    ctx: ReadContext, instrument_ids: Sequence[str], days: int, scope: bool = False
) -> EventCalendar:
    """The calendar of ``instrument_ids`` (plus the scope list when ``scope``) over the next
    ``days`` calendar days: one ``load_ahead`` for them all."""
    day = ctx.session.date
    end = day + timedelta(days=days)
    asked: list[str] = list(instrument_ids)
    unresolved: tuple[str, ...] = ()
    if scope:
        scoped = scoped_instruments(ctx.reader, ctx.configs, day, reasons=(LIST,))
        asked, unresolved = [*asked, *scoped.instrument_ids], scoped.unresolved
    wanted = list(dict.fromkeys(asked))
    known = load_instruments(ctx, wanted)
    names = tuple(CalendarName(i, known[i].symbol) for i in wanted if i in known)
    ahead = load_ahead(ctx, [n.instrument_id for n in names], end)
    funds = {i for i in wanted if i in known and known[i].is_etf}
    entries = [
        CalendarEvent(n.instrument_id, n.symbol, e)
        for n in names
        for e in ahead.by_name[n.instrument_id]
    ]
    entries += [CalendarEvent(None, None, e) for e in ahead.market]
    by_day: dict[date, list[CalendarEvent]] = {d: [] for d in sessions_between(day, end)}
    for entry in entries:
        by_day.setdefault(entry.event.date, []).append(entry)
    return EventCalendar(
        session=day,
        end=end,
        names=names,
        days=tuple(
            CalendarDay(d, is_session(d), tuple(found)) for d, found in sorted(by_day.items())
        ),
        gaps=(
            *(g for n in names for g in ahead.gaps[n.instrument_id] if not _fund_own(g, funds)),
            *ahead.market_gaps,
        ),
        missing=tuple(i for i in wanted if i not in known),
        unresolved=tuple(unresolved),
    )
