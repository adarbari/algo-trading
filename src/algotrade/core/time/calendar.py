"""The exchange calendar (NYSE): which days are sessions, and when each one closes.

The one place that knows weekends, holidays and early closes (ADR 0019, ``session-calendar``).
Pure Python. Rules (NYSE), valid for sessions from 1971 (the Monday-holiday rules of that
year; earlier years are not modelled: Washington's Birthday was February 22, and 1968 had
Wednesday paperwork-crisis closures and a state-wide election-day closure):

- full-day holidays: New Year's Day (Sunday -> Monday; Saturday -> not observed, the year-end
  session stays open), Martin Luther King Jr. Day (3rd Monday of January, from 1998: the NYSE
  stayed open on it before), Washington's Birthday (3rd Monday of February), Good Friday,
  Memorial Day (last Monday of May), Juneteenth (from 2022), Independence Day, Labor Day
  (1st Monday of September), Thanksgiving (4th Thursday of November) and Christmas;
  fixed-date holidays move Saturday -> Friday and Sunday -> Monday;
- special closures (``SPECIAL_CLOSURES``): days the exchange closed outside the rules since
  1971: presidential election days to 1980, days of mourning, a blackout, hurricanes and
  September 11;
- early closes (13:00 New York): July 3 and December 24 when they are sessions, and the day
  after Thanksgiving (the close times are the current ones; no earlier era is modelled).

Market-structure days by rule (the days the events-ahead read lists, ADR 0050): the monthly
option expiry (``monthly_expiry``: the third Friday, or the session before it when the exchange
is closed), the last session of a month (``last_session_of_month``: a quarter's end) and the
annual Russell US index reconstitution (``russell_reconstitution``: after the close of the
fourth Friday of June, or the session before it).

``last_closed_session(now)`` is the session a nightly run may ingest as end of day: the most
recent one whose close (plus a settle margin) has passed in New York time. A run started
during market hours therefore never treats today's intraday data as end of day.
"""

from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

EXCHANGE_TZ = ZoneInfo("America/New_York")
REGULAR_CLOSE = time(16, 0)
EARLY_CLOSE = time(13, 0)
DEFAULT_SETTLE = timedelta(minutes=30)
_MONDAY, _THURSDAY, _FRIDAY, _SATURDAY = 0, 3, 4, 5
_MLK_FROM_YEAR = 1998  # first NYSE closure for Martin Luther King Jr. Day: 1998-01-19
# Full-day closures outside the rules since 1971 (NYSE; cross-checked with the list in
# exchange_calendars' XNYS calendar and the NYSE's "Market Closings" history).
SPECIAL_CLOSURES: dict[date, str] = {
    date(1972, 11, 7): "presidential election day (closed through 1980)",
    date(1972, 12, 28): "national day of mourning, President Harry S. Truman",
    date(1973, 1, 25): "national day of mourning, President Lyndon B. Johnson",
    date(1976, 11, 2): "presidential election day (closed through 1980)",
    date(1977, 7, 14): "New York City blackout",
    date(1980, 11, 4): "presidential election day (closed through 1980)",
    date(1985, 9, 27): "Hurricane Gloria",
    date(1994, 4, 27): "national day of mourning, President Richard Nixon",
    date(2001, 9, 11): "September 11 attacks",
    date(2001, 9, 12): "September 11 attacks",
    date(2001, 9, 13): "September 11 attacks",
    date(2001, 9, 14): "September 11 attacks",
    date(2004, 6, 11): "national day of mourning, President Ronald Reagan",
    date(2007, 1, 2): "national day of mourning, President Gerald Ford",
    date(2012, 10, 29): "Hurricane Sandy",
    date(2012, 10, 30): "Hurricane Sandy",
    date(2018, 12, 5): "national day of mourning, President George H. W. Bush",
    date(2025, 1, 9): "national day of mourning, President Jimmy Carter",
}
_SPECIAL_BY_YEAR: dict[int, frozenset[date]] = {
    year: frozenset(d for d in SPECIAL_CLOSURES if d.year == year)
    for year in {d.year for d in SPECIAL_CLOSURES}
}


def is_weekend(day: date) -> bool:
    return day.weekday() >= _SATURDAY


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The ``n``-th ``weekday`` (Monday = 0) of a month; ``n = -1`` is the last one."""
    if n > 0:
        first = date(year, month, 1)
        return first + timedelta((weekday - first.weekday()) % 7 + 7 * (n - 1))
    last = date(year + month // 12, month % 12 + 1, 1) - timedelta(1)
    return last - timedelta((last.weekday() - weekday) % 7)


def third_friday(year: int, month: int) -> date:
    """The standard monthly option expiry day (before any holiday adjustment)."""
    return nth_weekday(year, month, _FRIDAY, 3)


def easter(year: int) -> date:
    """Western (Gregorian) Easter Sunday: the anonymous Gregorian computus."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(year, month, day + 1)


def _observed(day: date) -> date:
    """A fixed-date holiday on a weekend moves to the nearest weekday."""
    if day.weekday() == _SATURDAY:
        return day - timedelta(1)
    return day + timedelta(1) if day.weekday() == 6 else day


@lru_cache(maxsize=64)
def holidays(year: int) -> frozenset[date]:
    """Full-day exchange holidays in ``year``."""
    days = {
        nth_weekday(year, 2, _MONDAY, 3),
        easter(year) - timedelta(2),
        nth_weekday(year, 5, _MONDAY, -1),
        _observed(date(year, 7, 4)),
        nth_weekday(year, 9, _MONDAY, 1),
        nth_weekday(year, 11, _THURSDAY, 4),
        _observed(date(year, 12, 25)),
    }
    new_year = date(year, 1, 1)
    if new_year.weekday() != _SATURDAY:  # a Saturday New Year's Day is not observed
        days.add(_observed(new_year))
    if year >= _MLK_FROM_YEAR:
        days.add(nth_weekday(year, 1, _MONDAY, 3))
    if year >= 2022:
        days.add(_observed(date(year, 6, 19)))
    days.update(_SPECIAL_BY_YEAR.get(year, ()))
    return frozenset(days)


def is_session(day: date) -> bool:
    """Whether the exchange trades on ``day``."""
    return not is_weekend(day) and day not in holidays(day.year)


@lru_cache(maxsize=64)
def early_closes(year: int) -> frozenset[date]:
    """Sessions that close at 13:00 New York time."""
    candidates = (
        date(year, 7, 3),
        nth_weekday(year, 11, _THURSDAY, 4) + timedelta(1),
        date(year, 12, 24),
    )
    return frozenset(d for d in candidates if is_session(d))


def close_time(day: date) -> datetime:
    """When the session ``day`` closes, as an aware UTC datetime. ``day`` must be a session."""
    if not is_session(day):
        raise ValueError(f"{day} is not a session")
    local = EARLY_CLOSE if day in early_closes(day.year) else REGULAR_CLOSE
    return datetime.combine(day, local, EXCHANGE_TZ).astimezone(UTC)


def previous_session(day: date) -> date:
    """The last session strictly before ``day``."""
    day -= timedelta(1)
    while not is_session(day):
        day -= timedelta(1)
    return day


def next_session(day: date) -> date:
    """The first session strictly after ``day``."""
    day += timedelta(1)
    while not is_session(day):
        day += timedelta(1)
    return day


def sessions_between(start: date, end: date) -> list[date]:
    """Every session in ``[start, end]`` (inclusive), in order."""
    return [
        start + timedelta(i)
        for i in range((end - start).days + 1)
        if is_session(start + timedelta(i))
    ]


def sessions_ending(day: date, n: int) -> list[date]:
    """The ``n`` sessions ending at ``day`` (its last session on or before it), oldest first."""
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    last = day if is_session(day) else previous_session(day)
    out = [last]
    while len(out) < n:
        out.append(previous_session(out[-1]))
    return out[::-1]


def sessions_to(start: date, end: date) -> int:
    """How many sessions after ``start`` up to and including ``end`` (0 when ``end <= start``):
    the trading days until an event on ``end``, seen from ``start``."""
    if end <= start:
        return 0
    return len(sessions_between(start + timedelta(1), end))


def session_on_or_before(day: date) -> date:
    """``day`` when it is a session, else the last session before it."""
    return day if is_session(day) else previous_session(day)


def monthly_expiry(year: int, month: int) -> date:
    """The standard monthly equity option expiry: the third Friday, or the session before it
    when the exchange is closed on it (Good Friday, Juneteenth)."""
    return session_on_or_before(third_friday(year, month))


def last_session_of_month(year: int, month: int) -> date:
    """The month's last session (for March, June, September and December: the quarter's end)."""
    return session_on_or_before(date(year + month // 12, month % 12 + 1, 1) - timedelta(1))


def russell_reconstitution(year: int) -> date:
    """The annual Russell US index reconstitution, effective after the close: the fourth
    Friday of June (2018-06-22, 2024-06-28), or the session before it when closed."""
    return session_on_or_before(nth_weekday(year, 6, _FRIDAY, 4))


def exchange_date(now: datetime) -> date:
    """The calendar date in New York at ``now`` (an aware datetime)."""
    return now.astimezone(EXCHANGE_TZ).date()


def last_closed_session(now: datetime, settle: timedelta = DEFAULT_SETTLE) -> date:
    """The most recent session whose close plus ``settle`` is at or before ``now``."""
    day = exchange_date(now)
    if not is_session(day):
        day = previous_session(day)
    while close_time(day) + settle > now:
        day = previous_session(day)
    return day


OWNER_ZONE = "America/Los_Angeles"  # the zone of the owner's schedules (nightly deadlines)


def local_deadline(day: date, at: time, zone: str = OWNER_ZONE) -> datetime:
    """The instant ``day`` at wall-clock ``at`` in ``zone`` (DST-correct), as UTC."""
    return datetime.combine(day, at, tzinfo=ZoneInfo(zone)).astimezone(UTC)
