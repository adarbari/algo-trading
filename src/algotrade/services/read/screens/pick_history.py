"""A screener's picked count for each of its last N sessions (``Screener.pickHistory``): a
sparkline over the screens page.

A **ranged read** (ADR 0036 allows explicit ranges, as the regime bands and the market history
do): the window is the ``sessions`` exchange-calendar sessions ending at the request's resolved
session (``core.time.calendar.sessions_ending``), oldest first, one entry per session, never
skipped. Entry ``d`` is what ``latestRun`` says at session ``d`` (the latest run; the same
counts, ``is_picked`` / ``PAUSED``, whole run; where the session's latest record counted
nothing, ``latestRun`` itself is asked); a session
with no run of the screener is an entry with ``picked`` null and ``not_run`` saying why
(``NOT_RUN``), never an older run carried forward. Every session is read as it is stored now
(no ``as_of``: the same as ``latestRun`` at that session).

Cost: a screen writes about 13k result rows per screener per session, so the window is NOT
counted from result rows. The request's own session is ``latestRun`` itself (its rows are read
already); an earlier session is counted from its run record's decisions (``stats["summary"]``,
the whole run's count of each decision, written with the rows), the records of every asked
screener found in one pass over the run store, kept in the result cache until the next
publish."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from algotrade.core.time.calendar import sessions_ending
from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.context import ReadContext, at_session
from algotrade.services.read.screens.runs import (
    PAUSED,
    RULE_SCREEN,
    LatestRun,
    RunKey,
    ScreenerRun,
    is_picked,
    latest_run,
    load_latest_runs,
)
from algotrade.services.read.values import Unknown, UnknownCode
from algotrade.services.screening.run import run_job_name
from algotrade.storage.runs import RunRecord

DEFAULT_SESSIONS = 30
MAX_SESSIONS = 90  # a window asked for beyond it is cut to it
FINISHED = frozenset({"complete", "partial"})  # a screen that wrote its rows and its summary


@dataclass(frozen=True)
class PickCount:
    """One session of a screener's history: ``picked`` / ``paused`` of its latest run (None
    for both: no run in the session, ``not_run`` says why)."""

    session: date
    picked: int | None
    paused: int | None
    not_run: Unknown | None


def _decisions(record: RunRecord) -> Mapping[str, int] | None:
    """The run's count of each decision (None: a record that finished no screen)."""
    if record.finished_at is None or record.status.value not in FINISHED:
        return None
    found = (record.stats.get("summary") or {}).get("decisions") or record.stats.get("decisions")
    return None if found is None else {str(d): int(n) for d, n in found.items()}


def _records(ctx: ReadContext, jobs: frozenset[str], first: date, last: date) -> list[RunRecord]:
    """The screen records of ``jobs`` for ``first..last``, one pass, once per publish."""
    key = ("pick_history", first, last, tuple(sorted(jobs)), ctx.reader.visible_seq())
    found: list[RunRecord] | None = ctx.cache.get(key)  # key read first (ADR 0022)
    if found is None:
        found = ctx.reader.runs_of(jobs, first, last)
        ctx.cache.put(key, found)
    return found


def _not_run(config_id: str, day: date) -> PickCount:
    detail = f"{config_id} has no run in {RULE_SCREEN} for {day.isoformat()}"
    return PickCount(
        day, None, None, Unknown(UnknownCode.NOT_RUN, run_cause(config_id, detail, day))
    )


def _counted(day: date, decisions: Mapping[str, int]) -> PickCount:
    picked = sum(n for d, n in decisions.items() if is_picked(d))
    return PickCount(day, picked, decisions.get(PAUSED, 0), None)


def load_pick_histories(
    ctx: ReadContext, keys: Sequence[RunKey], sessions: int = DEFAULT_SESSIONS
) -> dict[RunKey, tuple[PickCount, ...]]:
    """For each ``(owner, config id)`` of ``keys`` its ``PickCount`` per session of the last
    ``sessions`` (cut to ``1..MAX_SESSIONS``) ending at the request's session, oldest first."""
    days = sessions_ending(ctx.session.date, min(max(sessions, 1), MAX_SESSIONS))
    today = load_latest_runs(ctx, keys) if days[-1] == ctx.session.date else {}
    jobs = {key: run_job_name(key[1], key[0]) for key in keys}
    records = _records(ctx, frozenset(jobs.values()), days[0], days[-1]) if len(days) > 1 else []
    latest: dict[tuple[str, date], RunRecord] = {}
    for record in records:  # by start time: the session's latest record is the last
        latest[(record.job, record.session_date)] = record
    return {
        key: tuple(_entry(ctx, key, job, day, today.get(key), latest) for day in days)
        for key, job in jobs.items()
    }


def _of_run(day: date, config_id: str, run: ScreenerRun | None) -> PickCount:
    if run is None:
        return _not_run(config_id, day)
    return PickCount(day, run.picked, run.paused, None)


def _entry(
    ctx: ReadContext,
    key: RunKey,
    job: str,
    day: date,
    todays: LatestRun | None,
    latest: Mapping[tuple[str, date], RunRecord],
) -> PickCount:
    """``key``'s entry for ``day``: the request's session is ``latestRun``; an earlier one its
    latest record's counts, or ``latestRun`` there when that record counted nothing (still
    running, failed: its rows are what ``latestRun`` shows); no record: ``NOT_RUN``."""
    if todays is not None and day == ctx.session.date:
        return _of_run(day, key[1], todays.run)
    record = latest.get((job, day))
    if record is None:
        return _not_run(key[1], day)
    decisions = _decisions(record)
    if decisions is not None:
        return _counted(day, decisions)
    return _of_run(day, key[1], latest_run(at_session(ctx, day), *key).run)
