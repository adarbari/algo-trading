"""The screener runs for the Admin "Screener runs" tab (``ScreenerRunEntry``): every screen run
record ``screen-<config>-<user>`` of every screener config (the site presets, and each user's own)
for the site and every declared user, of any status, newest first, with what each run recorded
about itself (version, hash, decisions, regime, the tables it ran without), and one run's frozen
comparison with the run before it.

Run records, not session data: the loaders take the session-free ``Stores`` context and read a run
as its record left it, never by session date. The list reads no result row; a figure the record
does not hold is ``None``, never 0 (a run that never finished has no decisions). The detail's
changes are the one ``results/screen_runs`` row of that run (``FrozenRun``), by run id."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from algotrade.config.site.settings import load_users
from algotrade.config.user import SITE_USER
from algotrade.services.read.availability.cause import Unavailable
from algotrade.services.read.availability.unavailable import unavailable_tables
from algotrade.services.read.context import Stores, run_partition
from algotrade.services.read.screens.pick_history import record_decisions
from algotrade.services.read.screens.runs import (
    FROZEN_COLUMNS,
    SCREEN_RUNS,
    DecisionCount,
    FrozenRun,
    frozen_summary,
    run_coverage,
)
from algotrade.services.screening.rule_results import PAUSED, is_picked
from algotrade.services.screening.run import run_job_name
from algotrade.storage.configs.files import SCREENERS
from algotrade.storage.runs import RunRecord, RunStatus

__all__ = [
    "HISTORY_DAYS",
    "RunStatus",  # the record's own enum: the GraphQL status enum serves it as is
    "ScreenerRunEntry",
    "load_screener_run",
    "load_screener_run_changes",
    "load_screener_runs",
]
PREFIX = "screen-"
WINDOW_DAYS = 7  # the list reads a week of sessions at a time, newest first
HISTORY_DAYS = 91  # ...and no further back than this: a run of an older session is not searched


@dataclass(frozen=True)
class ScreenerRunEntry:
    """One screener run. ``owner``: whose run (``site`` for the shared one); ``session``: the
    session it screened; ``status``: its record's (complete, partial, failed, running, ...);
    ``knowledge_ts``: when it committed (its start while it has not); ``config_version`` and
    ``config_hash``: what ran (None: not recorded); ``decisions``: every decision of the whole run
    with its count, most first (None: the run never finished, never 0), with ``picked`` and
    ``paused`` counted from them as the screens page does; ``regime``: the label it stamped (None:
    gate off, unknown); ``coverage``, ``missing_tables`` and ``missing_optional_tables``: as the
    record holds them; ``unavailable``: what those tables leave out (ADR 0056)."""

    run_id: str
    config_id: str
    owner: str
    session: date
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None
    knowledge_ts: datetime
    config_version: int | None
    config_hash: str | None
    decisions: tuple[DecisionCount, ...] | None
    picked: int | None
    paused: int | None
    regime: str | None
    coverage: str | None
    missing_tables: tuple[str, ...]
    missing_optional_tables: tuple[str, ...]
    unavailable: tuple[Unavailable, ...]


def _text(value: object) -> str | None:
    return None if value is None else str(value)


def _version(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _entry(record: RunRecord, config_id: str, owner: str) -> ScreenerRunEntry:
    stats: dict[str, Any] = dict(record.stats)
    found = record_decisions(record)
    coverage, missing, optional = run_coverage(stats)
    regime = stats.get("regime")
    return ScreenerRunEntry(
        run_id=record.run_id,
        config_id=config_id,
        owner=owner,
        session=record.session_date,
        status=record.status,
        started_at=record.started_at,
        finished_at=record.finished_at,
        knowledge_ts=record.finished_at or record.started_at,
        config_version=_version(stats.get("config_version")),
        config_hash=_text(stats.get("config_hash")),
        decisions=None
        if found is None
        else tuple(
            DecisionCount(d, n) for d, n in sorted(found.items(), key=lambda dn: (-dn[1], dn[0]))
        ),
        picked=None if found is None else sum(n for d, n in found.items() if is_picked(d)),
        paused=None if found is None else found.get(PAUSED, 0),
        regime=_text(regime.get("label")) if isinstance(regime, dict) else None,
        coverage=coverage,
        missing_tables=missing,
        missing_optional_tables=optional,
        unavailable=unavailable_tables([*missing, *optional], record.session_date),
    )


def _jobs(ctx: Stores) -> dict[str, tuple[str, str]]:
    """``{run record job: (config id, owner)}`` of every screen the site and each declared user
    can run now: the site presets for each of them, and a user's own finalised screeners (a run of
    a config or user no longer declared is not listed)."""
    users = dict.fromkeys([SITE_USER, *(u.user_id for u in load_users(ctx.configs).users)])
    site = ctx.configs.names(SITE_USER, SCREENERS)
    return {
        run_job_name(config, user): (config, user)
        for user in users
        for config in sorted(
            {*site, *(ctx.configs.names(user, SCREENERS) if user != SITE_USER else ())}
        )
    }


def load_screener_runs(
    ctx: Stores,
    limit: int = 50,
    user: str | None = None,
    screener: str | None = None,
    status: RunStatus | None = None,
) -> tuple[ScreenerRunEntry, ...]:
    """The ``limit`` most recent screen runs of any status, newest session first (then newest
    start), read a window of sessions at a time, stopping once ``limit`` match or ``HISTORY_DAYS``
    of sessions are read: ``user`` (whose), ``screener`` (config id) and ``status`` (the record's)
    narrow it. The order is by the session a run screened, not by when it started: a backfill of
    an old session started today sorts below newer sessions and, once ``limit`` newer runs match,
    is not listed."""
    jobs = {
        job: key
        for job, key in _jobs(ctx).items()
        if user in (None, key[1]) and screener in (None, key[0])
    }
    want = max(limit, 1)
    found: list[ScreenerRunEntry] = []
    for first, last in _windows(datetime.now(UTC).date()):
        found.extend(
            _entry(r, *jobs[r.job])
            for r in ctx.reader.runs_of(set(jobs), first, last)
            if status in (None, r.status)
        )
        if len(found) >= want:
            break  # the older windows hold only older sessions: never read
    found.sort(key=lambda r: (r.session, r.started_at), reverse=True)
    return tuple(found[:want])


def _windows(today: date) -> Iterator[tuple[date, date]]:
    """Session windows newest first: ``WINDOW_DAYS`` each, back from ``today`` to ``HISTORY_DAYS``
    (a small ``limit`` stops at the first that fills it; no window reads a session before them)."""
    last = today
    for _ in range(-(-HISTORY_DAYS // WINDOW_DAYS)):
        first = last - timedelta(days=WINDOW_DAYS - 1)
        yield first, last
        last = first - timedelta(days=1)


def load_screener_run(ctx: Stores, run_id: str) -> ScreenerRunEntry | None:
    """The screen run ``run_id``; ``None`` when there is none (or it is another job's)."""
    record = _record(ctx, run_id)
    if record is None:
        return None
    config_id, owner = _identity(ctx, record)
    return _entry(record, config_id, owner)


def _record(ctx: Stores, run_id: str) -> RunRecord | None:
    try:
        record = ctx.reader.run(run_id)
    except ValueError:  # not a valid storage key
        return None
    return record if record is not None and record.job.startswith(PREFIX) else None


def _identity(ctx: Stores, record: RunRecord) -> tuple[str, str]:
    """(config id, owner) of a screen record: the run's own stats, else the declared pair whose
    job it is, else the job name split at its last dash."""
    stats = record.stats
    if stats.get("config_id") and stats.get("user"):
        return str(stats["config_id"]), str(stats["user"])
    known = _jobs(ctx).get(record.job)
    if known is not None:
        return known
    config_id, _, owner = record.job.removeprefix(PREFIX).rpartition("-")
    return config_id, owner


def load_screener_run_changes(ctx: Stores, run_id: str) -> FrozenRun | None:
    """What the run ``run_id`` froze when it wrote: its ``results/screen_runs`` row (picked and
    paused counts, the run it was compared with, new and dropped against it; a count None: no
    previous run). ``None``: no such run, or it has no row (never 0)."""
    record = _record(ctx, run_id)
    if record is None:
        return None
    config_id, owner = _identity(ctx, record)
    rows = run_partition(ctx, SCREEN_RUNS, record, ("user_id", "config_id", *FROZEN_COLUMNS))
    if rows is None:
        return None
    mine = rows[(rows["user_id"] == owner) & (rows["config_id"] == config_id)]
    if mine.empty:
        return None
    return frozen_summary(mine.iloc[-1]).frozen
