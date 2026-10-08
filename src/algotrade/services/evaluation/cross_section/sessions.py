"""The sessions an edge is evaluated on (ADR 0053 and its amendment of 2026-10-08).

A row has a decision session D (the screen, the eligible names, the implied vol and the event
set are read at D) and an entry session S > D (the outcome is the partition at S: the window
starts at S's close). ``decision_sessions`` gives the D of a schedule, spaced at least one
horizon apart so the windows do not overlap and the sessions are independent:

- ``every_session``: the first session, then every ``h``-th session after it
- ``month_end``: the last session of each calendar month, thinned greedily so consecutive
  ones are at least ``h`` sessions apart (a month cut short by the range's end is not one)
- ``on_event:<class>``: every session is a candidate; ``events.py`` says which have events and
  ``event_blocks`` pools them into blocks of ``h`` sessions

``entry_session`` is S = D + the document's ``start_offset_sessions``; for an event schedule
S = anchor + offset and D = S - 1, so S = D + 1.
"""

from collections.abc import Sequence
from datetime import date

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import next_session
from algotrade.engines.selection.schedule import rebalance_sessions


def decision_sessions(schedule: str, sessions: Sequence[date], horizon: int) -> list[date]:
    """The decision sessions D of a non-event ``schedule`` among ``sessions`` (ascending
    exchange sessions), for windows of ``horizon`` sessions."""
    if horizon < 1:
        raise ConfigurationError(f"horizon must be >= 1 session, got {horizon}")
    if schedule.startswith("on_event:"):
        raise ConfigurationError(f"schedule {schedule!r} is read through events.py, not here")
    if not sessions:
        return []
    if schedule == "every_session":
        return rebalance_sessions(sessions[0], sessions, f"{horizon}d")
    if schedule == "month_end":
        return _spaced(_month_ends(sessions), sessions, horizon)
    raise ConfigurationError(f"unknown schedule {schedule!r}")


def entry_session(decision: date, offset: int) -> date:
    """S: ``offset`` (>= 1) sessions after the decision session D."""
    if offset < 1:
        raise ConfigurationError(f"the entry session is at least 1 after the decision: {offset}")
    day = decision
    for _ in range(offset):
        day = next_session(day)
    return day


def event_blocks(
    event_days: Sequence[date], sessions: Sequence[date], horizon: int
) -> list[list[date]]:
    """``event_days`` (ascending decision sessions with events) pooled into blocks: a day joins
    the current block when it is fewer than ``horizon`` sessions after the block's FIRST day, so a
    block spans at most ``horizon`` sessions and is one statistic. Measured from the last day,
    daily events (earnings) chained the whole history into one block (2026-10-08: one
    "independent session" over two years). A window starting near a block's end can overlap the
    next block's first windows by up to ``horizon - 1`` sessions: at most one boundary overlap,
    the price of keeping every event (ADR 0053 amendment, item 7)."""
    if horizon < 1:
        raise ConfigurationError(f"horizon must be >= 1 session, got {horizon}")
    position = {day: i for i, day in enumerate(sessions)}
    blocks: list[list[date]] = []
    for day in sorted(event_days):
        if blocks and position[day] - position[blocks[-1][0]] < horizon:
            blocks[-1].append(day)
        else:
            blocks.append([day])
    return blocks


def _month_ends(sessions: Sequence[date]) -> list[date]:
    """The last session of each month, when the month really ends there."""
    return [
        day
        for day, following in zip(
            sessions, [*sessions[1:], next_session(sessions[-1])], strict=True
        )
        if (day.year, day.month) != (following.year, following.month)
    ]


def _spaced(candidates: Sequence[date], sessions: Sequence[date], horizon: int) -> list[date]:
    position = {day: i for i, day in enumerate(sessions)}
    kept: list[date] = []
    for day in candidates:
        if not kept or position[day] - position[kept[-1]] >= horizon:
            kept.append(day)
    return kept
