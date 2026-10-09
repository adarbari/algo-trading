"""A screener's picked count for each of its last N sessions (``Screener.pickHistory``): a
sparkline over the screens page.

A **ranged read** (ADR 0036 allows explicit ranges, as the regime bands and the market history
do): the window is the ``sessions`` exchange-calendar sessions ending at the request's resolved
session (``core.time.calendar.sessions_ending``), oldest first, one entry per session, never
skipped. Each session is read as its own session: a session with no run of the screener is an
entry with ``picked`` null and ``not_run`` saying why (``NOT_RUN``), never an older run carried
forward. Several runs in one session resolve by the one run-selection rule of the screen read
(``runs.last_run_rows``: the latest ``knowledge_ts``), and the counts are the latest run's
(``is_picked`` / ``PAUSED``, whole run).

Point in time (ADR 0007): the request's own session is read as ``latestRun`` reads it (its
nightly run is stored after the close). An earlier session is read ``as_of`` the close of the
request's session, so a re-run of an old session stored after it is not read back into what
that session knew. One read of ``results/rule_screen`` (three columns) serves every screener
asked for (one batch for a list); a request costs that read of a window of partitions, kept in
the result cache until the next publish."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.core.time.calendar import close_time, sessions_ending
from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.context import ReadContext, partition_range
from algotrade.services.read.screens.runs import (
    PAUSED,
    RULE_SCREEN,
    RunKey,
    is_picked,
    last_run_rows,
    screen_rows,
)
from algotrade.services.read.values import Unknown, UnknownCode

DEFAULT_SESSIONS = 30
MAX_SESSIONS = 90  # a window asked for beyond it is cut to it
COLUMNS = ("user_id", "config_id", "decision")


@dataclass(frozen=True)
class PickCount:
    """One session of a screener's history: ``picked`` / ``paused`` of its latest run (None
    for both: no run in the session, ``not_run`` says why)."""

    session: date
    picked: int | None
    paused: int | None
    not_run: Unknown | None


def _window(ctx: ReadContext, days: Sequence[date]) -> pd.DataFrame:
    """The window's rows of every rule screen, ``session_date`` as a date: the earlier
    sessions as the store held them at the close of the request's session (``as_of``: the run
    selection of the table's run mode, ADR 0007), read once per publish; the request's own
    session through ``screen_rows`` (the read ``latestRun`` shares)."""
    key = ("pick_history", days[0], days[-1], ctx.reader.own_run, ctx.reader.visible_seq())
    found: pd.DataFrame | None = ctx.cache.get(key)  # key read first (ADR 0022)
    if found is None:
        parts: list[pd.DataFrame | None] = []
        if len(days) > 1:
            cutoff = close_time(days[-1])
            parts.append(partition_range(ctx, RULE_SCREEN, days[0], days[-2], cutoff, COLUMNS))
        today = screen_rows(ctx)
        parts.append(None if isinstance(today, Unknown) else today)
        columns = [*COLUMNS, "session_date", "run_id", "knowledge_ts"]
        frames = [p[columns] for p in parts if p is not None and not p.empty]
        found = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)
        found["session_date"] = pd.to_datetime(found["session_date"]).dt.date
        ctx.cache.put(key, found)
    return found


def _count(config_id: str, day: date, rows: pd.DataFrame | None) -> PickCount:
    if rows is None:
        detail = f"{config_id} has no run in {RULE_SCREEN} for {day.isoformat()}"
        why = Unknown(UnknownCode.NOT_RUN, run_cause(config_id, detail, day))
        return PickCount(day, None, None, why)
    _, run = last_run_rows(rows)
    decisions = run["decision"].astype(str)
    return PickCount(
        day, int(sum(is_picked(d) for d in decisions)), int((decisions == PAUSED).sum()), None
    )


def load_pick_histories(
    ctx: ReadContext, keys: Sequence[RunKey], sessions: int = DEFAULT_SESSIONS
) -> dict[RunKey, tuple[PickCount, ...]]:
    """For each ``(owner, config id)`` of ``keys`` its ``PickCount`` per session of the last
    ``sessions`` (cut to ``1..MAX_SESSIONS``) ending at the request's session, oldest first."""
    days = sessions_ending(ctx.session.date, min(max(sessions, 1), MAX_SESSIONS))
    stored = _window(ctx, days)
    groups = {
        (str(o), str(c), d): rows
        for (o, c, d), rows in stored.groupby(["user_id", "config_id", "session_date"])
    }
    return {
        (owner, config_id): tuple(
            _count(config_id, d, groups.get((owner, config_id, d))) for d in days
        )
        for owner, config_id in keys
    }
