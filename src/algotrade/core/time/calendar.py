"""The exchange calendar (NYSE): which days are sessions, and when each one closes.

The one place that knows weekends, holidays and early closes (ADR 0019, ``session-calendar``).
Pure Python. Rules (NYSE, current since 2022):

- full-day holidays: New Year's Day (Sunday -> Monday; Saturday -> not observed, the year-end
  session stays open), Martin Luther King Jr. Day (3rd Monday of January), Washington's
  Birthday (3rd Monday of February), Good Friday, Memorial Day (last Monday of May),
  Juneteenth (from 2022), Independence Day, Labor Day (1st Monday of September), Thanksgiving
  (4th Thursday of November) and Christmas; fixed-date holidays move Saturday -> Friday and
  Sunday -> Monday;
- special closures (``SPECIAL_CLOSURES``): days the exchange closed outside the rules, e.g.
  national days of mourning;
- early closes (13:00 New York): July 3 and December 24 when they are sessions, and the day
  after Thanksgiving.

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
# Full-day closures outside the rules (NYSE): national days of mourning.
SPECIAL_CLOSURES: dict[date, str] = {
    date(2018, 12, 5): "national day of mourning, President George H. W. Bush",
    date(2025, 1, 9): "national day of mourning, President Jimmy Carter",
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
        nth_weekday(year, 1, _MONDAY, 3),
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
    if year >= 2022:
        days.add(_observed(date(year, 6, 19)))
    days.update(d for d in SPECIAL_CLOSURES if d.year == year)
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
