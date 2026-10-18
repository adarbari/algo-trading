"""Calendar windows: stretches of sessions the exchange calendar fixes ahead of time (ADR 0053).

The closed set of windows an edge may use as ``schedule = "calendar:<window>"``. Each window has
a fixed length in sessions and a rule that places it from the calendar alone (``calendar.py``:
the monthly expiry, a month's last session, the holidays), so the rule never needs a fact that
is not known ahead of the window (no event-dated window: a macro release is ``on_event``).
A window is its list of sessions; its entry session S is the session before the first one (the
outcome window starts at S's close) and its decision session D is the one before S.

- ``turn_of_month``: the month's last session and the three after it (S: the session before the
  last), 4 sessions
- ``opex_week``: the 5 sessions ending on the month's option expiry (Monday to Friday; after a
  Thursday expiry the window starts on the Friday before)
- ``quarter_end``: the last 5 sessions of March, June, September and December
- ``pre_holiday``: the session before a scheduled full-day holiday (an unscheduled closure, such
  as a day of mourning or a storm, was not known ahead and is no holiday here), 1 session

Windows of one kind never overlap: ``turn_of_month`` windows are a month apart, ``opex_week``
windows end on different months' expiries, ``quarter_end`` windows a quarter apart and
``pre_holiday`` windows are single sessions of distinct days.
Pure Python, no pandas.
"""

from datetime import date

from algotrade.core.time.calendar import (
    SPECIAL_CLOSURES,
    holidays,
    last_session_of_month,
    monthly_expiry,
    next_session,
    previous_session,
    sessions_ending,
)

CALENDAR = "calendar:"
WINDOW_LENGTHS: dict[str, int] = {
    "turn_of_month": 4,
    "opex_week": 5,
    "quarter_end": 5,
    "pre_holiday": 1,
}
WINDOW_NAMES = tuple(WINDOW_LENGTHS)
_QUARTER_MONTHS = (3, 6, 9, 12)


def window_name(schedule: str) -> str | None:
    """The window of a ``calendar:<window>`` schedule (any text after the prefix), else None."""
    return schedule.removeprefix(CALENDAR) if schedule.startswith(CALENDAR) else None


def window_length(name: str) -> int:
    """The sessions in window ``name``; ``KeyError`` for a name outside the closed set."""
    return WINDOW_LENGTHS[name]


def _starting_at(day: date, length: int) -> list[date]:
    out = [day]
    while len(out) < length:
        out.append(next_session(out[-1]))
    return out


def _holiday_eves(year: int) -> list[date]:
    """The sessions before the scheduled full-day holidays of ``year``."""
    scheduled = sorted(d for d in holidays(year) if d not in SPECIAL_CLOSURES and d.weekday() < 5)
    return sorted({previous_session(d) for d in scheduled})


def _year_windows(name: str, year: int) -> list[list[date]]:
    if name == "turn_of_month":
        return [_starting_at(last_session_of_month(year, m), 4) for m in range(1, 13)]
    if name == "opex_week":
        return [sessions_ending(monthly_expiry(year, m), 5) for m in range(1, 13)]
    if name == "quarter_end":
        return [sessions_ending(last_session_of_month(year, m), 5) for m in _QUARTER_MONTHS]
    if name == "pre_holiday":
        return [[d] for d in _holiday_eves(year)]  # January 1's eve is in the year before
    raise KeyError(name)


def windows(name: str, first: date, last: date) -> list[list[date]]:
    """The windows of kind ``name`` whose sessions all lie in ``[first, last]``, in order, each as
    its list of sessions."""
    if name not in WINDOW_LENGTHS:
        raise KeyError(name)
    found = {
        tuple(w)
        for year in range(first.year - 1, last.year + 2)
        for w in _year_windows(name, year)
        if w[0] >= first and w[-1] <= last
    }  # a set: the eve of January 1 comes from two years
    return [list(w) for w in sorted(found)]


def entry_session(window: list[date]) -> date:
    """S of a window: the session before its first (the outcome starts at S's close)."""
    return previous_session(window[0])


def decision_session(window: list[date]) -> date:
    """D of a window: the session before S (the screen runs on D, after its close)."""
    return previous_session(entry_session(window))
