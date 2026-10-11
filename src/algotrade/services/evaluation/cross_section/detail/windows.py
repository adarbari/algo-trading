"""The calendar facts of an edge evaluation's measured blocks (ADR 0064 decisions 1 and 7): the
entry and exit sessions of each block of decision sessions, the unit of the outcome's value, and
the projected exits of a calendar schedule (the exit sessions of its next decision sessions
beyond the last measured one, with the scheduled and measured decision-session counts the read
model scales them by). Pure arithmetic over the trading calendar and the document's schedule;
the harness owns it because only it knows the schedule, and a reader never re-derives it."""

import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from algotrade.config.edges.document import Edge
from algotrade.config.edges.verdict import VerdictSettings
from algotrade.core.time.calendar import sessions_between
from algotrade.services.evaluation.cross_section.hit import is_return
from algotrade.services.evaluation.cross_section.measures import SessionStat
from algotrade.services.evaluation.cross_section.sessions import (
    Leg,
    decision_sessions,
    entry_session,
)

PROJECTION_SHARE = 0.25  # the floor of the fill ratio the outlook scales by (ADR 0064, decision 7)
SESSIONS_PER_YEAR, MONTH_SESSIONS = 250, 21
EXCESS_RETURN, RETURN, CUSHION, RATIO = "excess_return", "return", "cushion", "ratio"


@dataclass(frozen=True)
class BlockWindow:
    """One measured block of decision sessions: the first leg's entry session S, the last leg's
    exit (S + the horizon, from the calendar), how many decision sessions it pools (an event
    block; 1 otherwise) and the table a leg of it was lost to, if one was."""

    entry: date
    exit: date
    days: int = 1
    lost_table: str | None = None


@dataclass(frozen=True)
class Projection:
    """What the outlook needs of a calendar schedule: ``exits`` the exit sessions of the next
    decision sessions after the last measured exit, and how many decision sessions were
    scheduled (their window closed) and measured (not excluded) over the out-of-sample side
    (None without a split) and over the whole run."""

    exits: tuple[date, ...]
    scheduled_oos: int | None
    measured_oos: int | None
    scheduled: int
    measured: int


@dataclass(frozen=True)
class SeriesFacts:
    """What the series and the projection of one variant at one horizon need beyond its stats:
    ``windows`` align with the variant's block stats, ``unit`` is what their values measure,
    ``projection`` is None for an event schedule (it cannot be projected)."""

    windows: tuple[BlockWindow, ...]
    unit: str
    projection: Projection | None = None


def unit_of(edge: Edge) -> str:
    """What an oriented value of ``edge``'s outcome is: an excess return over the benchmark, a
    plain return (no benchmark), the cushion to the nearest strike or a vol ratio."""
    o = edge.outcome
    if o.kind == "expires_otm":
        return CUSHION
    if is_return(edge):
        return RETURN if o.benchmark == "none" else EXCESS_RETURN
    return RATIO


def counts_wins(unit: str | None) -> bool:
    """Whether the trial statistics of a value in ``unit`` read the session's excess wins, not the
    value (ADR 0064 amendment 2026-10-11): a cushion or a ratio is not a return."""
    return unit in (CUSHION, RATIO)


def exit_session(entry: date, horizon: int) -> date:
    """The close of the window that starts at ``entry``: ``horizon`` sessions later."""
    return entry_session(entry, horizon)


def projection_count(settings: VerdictSettings) -> int:
    """N decision sessions to project: enough for the largest count a criterion asks of the
    out-of-sample side if only a quarter of the scheduled sessions were measured."""
    most = max(settings.min_oos_trades, settings.works_oos_trades, settings.works_trades)
    return math.ceil(most / PROJECTION_SHARE)


def next_exits(
    schedule: str, offset: int, horizon: int, start: date, after: date | None, count: int
) -> tuple[date, ...]:
    """The exit sessions of the next ``count`` decision sessions of a calendar ``schedule``
    (anchored at the range's ``start`` as the run's own are) whose window closes after ``after``
    (None: every one). The schedule is extended as far as ``count`` decisions need."""
    # Sessions enough for ``count`` decisions a horizon apart (a month_end one is a month at
    # least) beyond ``after``, with a margin; the bound follows the data, never a fixed span.
    sessions = int((count * max(horizon, MONTH_SESSIONS) + SESSIONS_PER_YEAR) * 1.3)
    reach = ((after or start) - start).days + sessions * 366 // SESSIONS_PER_YEAR + 366
    found: list[date] = []
    days = sessions_between(start, start + timedelta(days=reach))
    for d in decision_sessions(schedule, days, horizon):
        close = exit_session(entry_session(d, offset), horizon)
        if after is None or close > after:
            found.append(close)
            if len(found) == count:
                break
    return tuple(found)


def plan_exits(
    edge: Edge,
    blocks: Sequence[Sequence[Leg]],
    closed: Collection[date],
    horizon: int,
    start: date,
    count: int,
) -> tuple[list[Sequence[Leg]], tuple[date, ...] | None]:
    """The blocks of one scope at one horizon with a closed leg (the measured ones) and its
    projected exits after the last of their windows; None for an event schedule (``on_event:``:
    when the next event falls is not known, the honest state is UNPROJECTABLE)."""
    kept = [b for b in blocks if any(leg.entry in closed for leg in b)]
    if edge.schedule.startswith("on_event:"):
        return kept, None
    last = max((exit_session(leg.entry, horizon) for b in kept for leg in b), default=None)
    offset = edge.outcome.start_offset_sessions
    return kept, next_exits(edge.schedule, offset, horizon, start, last, count)


def _measured(stats: Sequence[SessionStat]) -> int:
    return sum(1 for s in stats if not s.excluded_coverage)


def series_facts(
    edge: Edge,
    kept: Sequence[Sequence[Leg]],
    closed: Collection[date],
    horizon: int,
    stats: Sequence[SessionStat],
    lost: Mapping[date, str],
    split: date | None,
    exits: tuple[date, ...] | None,
) -> SeriesFacts:
    """The facts of one variant: ``kept`` are the blocks its ``stats`` pool (aligned), ``closed``
    the entry sessions whose outcome is stored, ``lost`` the table each lost decision session
    lacked, ``exits`` the scope's ``plan_exits``."""
    windows = []
    for block in kept:
        legs = [leg for leg in block if leg.entry in closed]
        windows.append(
            BlockWindow(
                entry=legs[0].entry,
                exit=exit_session(legs[-1].entry, horizon),
                days=len(legs),
                lost_table=next((lost[leg.decision] for leg in legs if leg.decision in lost), None),
            )
        )
    projection = None
    if exits is not None:
        oos = [s for s in stats if split is not None and s.session >= split]
        projection = Projection(
            exits=exits,
            scheduled_oos=None if split is None else len(oos),
            measured_oos=None if split is None else _measured(oos),
            scheduled=len(stats),
            measured=_measured(stats),
        )
    return SeriesFacts(tuple(windows), unit_of(edge), projection)
