"""The start sessions an edge is evaluated on: its schedule's sessions, spaced at least one
horizon apart so the windows do not overlap and the sessions are independent (ADR 0053).

- ``every_session``: the first session, then every ``h``-th session after it
- ``month_end``: the last session of each calendar month, thinned greedily so consecutive
  ones are at least ``h`` sessions apart (a month cut short by the range's end is not one)
- ``on_event:<class>``: arrives with ED4 (the events and their ``known_from``)
"""

from collections.abc import Sequence
from datetime import date

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import next_session
from algotrade.engines.selection.schedule import rebalance_sessions


def edge_sessions(schedule: str, sessions: Sequence[date], horizon: int) -> list[date]:
    """The start sessions of ``schedule`` among ``sessions`` (ascending exchange sessions),
    for windows of ``horizon`` sessions."""
    if horizon < 1:
        raise ConfigurationError(f"horizon must be >= 1 session, got {horizon}")
    if schedule.startswith("on_event:"):
        raise ConfigurationError(f"schedule {schedule!r} arrives with ED4 (event schedules)")
    if not sessions:
        return []
    if schedule == "every_session":
        return rebalance_sessions(sessions[0], sessions, f"{horizon}d")
    if schedule == "month_end":
        return _spaced(_month_ends(sessions), sessions, horizon)
    raise ConfigurationError(f"unknown schedule {schedule!r}")


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
