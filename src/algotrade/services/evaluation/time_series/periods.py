"""The periods of a time-series edge (ADR 0073): the windows of a ``calendar:<window>`` schedule
and, beside them, the stretches of the same length outside every window, tiled from the session
after each window (``core/time/windows.py``). A period is one unit for every count: it carries
its first session, its entry session S (the outcome starts at S's close) and its decision
session D (the one before S), all fixed by the calendar, so nothing here reads data and no period
placed in a range depends on anything after the range's end."""

from dataclasses import dataclass
from datetime import date, timedelta

from algotrade.core.time.windows import (
    decision_session,
    entry_session,
    out_of_window_stretches,
    window_length,
    windows,
)

_REACH = timedelta(days=60)  # a window starting later cannot touch a stretch ending by ``last``


@dataclass(frozen=True)
class Period:
    first: date  # its first session
    entry: date  # S
    decision: date  # D
    inside: bool  # a window of the schedule (else an out-of-window stretch)


def _period(sessions: list[date], inside: bool) -> Period:
    return Period(sessions[0], entry_session(sessions), decision_session(sessions), inside)


def periods(name: str, first: date, last: date) -> list[Period]:
    """The windows of kind ``name`` wholly in ``[first, last]`` and the out-of-window stretches
    of their length that end by ``last``, in order of their first session. A stretch avoids
    every window of the calendar, also one that begins after ``last``."""
    placed = windows(name, first, last)
    occupied = windows(name, first, last + _REACH)
    out = out_of_window_stretches(occupied, window_length(name), last)
    found = [*(_period(w, True) for w in placed), *(_period(s, False) for s in out)]
    return sorted(found, key=lambda p: p.first)
