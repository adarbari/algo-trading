"""A screener's last few runs for the run line and session strip of its results page
(``Screener.recentRuns``): one entry per exchange session of a window ending at the request's
resolved session, oldest first, each saying whether the screener ran (COMPLETE), ran with a gap
(PARTIAL) or did not run (NOT_RUN), what it picked and what changed since its previous run, and
what it left out, in public words.

An explicit **history** (ADR 0036 allows ranged reads, as ``pick_history`` does): every entry is
the run as its run record and ``screen_runs`` row left it, read as stored now; the request's own
session is ``latestRun`` itself (the one-session rule keeps it), an earlier one is never carried
forward into a later session. A session with no run is an entry with ``state`` NOT_RUN and
``not_run`` saying why (``Unknown``, never zero counts); a count that was not stored (the
new / dropped of a run before the ``screen_runs`` table) is None, never 0.

Bounded: at most ``MAX_LIMIT`` sessions; the request's session comes from the one latest-run read
the page makes anyway, earlier ones from the run records of every asked screener found in one
cached pass over the run store (``pick_history.screen_records``) and, for the change counts, one
small ``screen_runs`` read per session; never a result row of an earlier session."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from algotrade.core.time.calendar import sessions_ending
from algotrade.services.read.availability.cause import Unavailable, run_cause
from algotrade.services.read.availability.unavailable import unavailable_tables
from algotrade.services.read.context import ReadContext, at_session
from algotrade.services.read.screens.pick_history import record_decisions, screen_records
from algotrade.services.read.screens.results import load_change_summary
from algotrade.services.read.screens.runs import (
    RULE_SCREEN,
    SCREEN_RUNS,
    RunKey,
    ScreenerRun,
    latest_run,
    load_latest_runs,
    run_coverage,
)
from algotrade.services.read.values import Unknown, UnknownCode, to_scalar
from algotrade.services.screening.rule_results import PAUSED, UNKNOWN, is_picked
from algotrade.services.screening.run import run_job_name
from algotrade.storage.runs import RunRecord

DEFAULT_LIMIT = 10
MAX_LIMIT = 10  # a window asked for beyond it is cut to it


class RunState(StrEnum):
    """What the strip draws for a session: the screener ran to the end, ran with a gap (its
    run record says PARTIAL, or has no record to say otherwise: never claimed complete), or
    did not run."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    NOT_RUN = "NOT_RUN"


@dataclass(frozen=True)
class RecentRun:
    """One session of the window. Everything but ``session``, ``state`` and ``served`` is None
    (or empty) for a session with no run, and ``not_run`` says why. ``new_picks`` / ``dropped``:
    against the run's previous run (None: none, or not stored). ``left_out_share``: the share
    of the run's names it could not judge for want of a value (0..1; None: not counted).
    ``unavailable``: what the tables the run went without leave out (ADR 0056)."""

    session: date
    state: RunState
    served: bool  # the request's own session (the page's one served session, ADR 0036)
    run_id: str | None = None
    config_version: int | None = None
    picked: int | None = None
    paused: int | None = None
    new_picks: int | None = None
    dropped: int | None = None
    left_out_share: float | None = None
    unavailable: tuple[Unavailable, ...] = ()
    not_run: Unknown | None = None


def _int(value: object) -> int | None:
    found = to_scalar(value)
    return None if found is None else int(found)


def _share(decisions: Mapping[str, int]) -> float | None:
    total = sum(decisions.values())
    return None if total == 0 else decisions.get(UNKNOWN, 0) / total


def _not_run(config_id: str, day: date, served: bool) -> RecentRun:
    detail = f"{config_id} has no run in {RULE_SCREEN} for {day.isoformat()}"
    why = Unknown(UnknownCode.NOT_RUN, run_cause(config_id, detail, day))
    return RecentRun(day, RunState.NOT_RUN, served, not_run=why)


def _state(status: str | None, coverage: str | None) -> RunState:
    done = status == "complete" and coverage in (None, "COMPLETE")
    return RunState.COMPLETE if done else RunState.PARTIAL


def _of_run(run: ScreenerRun, served: bool, counts: tuple[int | None, int | None]) -> RecentRun:
    return RecentRun(
        session=run.session,
        state=_state(run.status, run.coverage),
        served=served,
        run_id=run.run_id,
        config_version=run.config_version,
        picked=run.picked,
        paused=run.paused,
        new_picks=counts[0],
        dropped=counts[1],
        left_out_share=_share({d.decision: d.count for d in run.decisions}),
        unavailable=run.unavailable,
    )


def _served(ctx: ReadContext, run: ScreenerRun) -> RecentRun:
    """The request's session: ``latestRun`` with its changes as ``Screener.changes``."""
    changes = {c.change: c.count for c in load_change_summary(ctx, run).counts}
    return _of_run(run, True, (changes.get("new"), changes.get("dropped")))


def _of_record(
    day: date,
    record: RunRecord,
    decisions: Mapping[str, int],
    counts: tuple[int | None, int | None],
) -> RecentRun:
    """An earlier session from its run record: the status and coverage it stored, the counts of
    its decisions (the whole run) and the version that ran."""
    coverage, missing, optional = run_coverage(record.stats)
    return RecentRun(
        session=day,
        state=_state(record.status.value, coverage),
        served=False,
        run_id=record.run_id,
        config_version=_int(record.stats.get("config_version")),
        picked=sum(n for d, n in decisions.items() if is_picked(d)),
        paused=decisions.get(PAUSED, 0),
        new_picks=counts[0],
        dropped=counts[1],
        left_out_share=_share(decisions),
        unavailable=unavailable_tables([*missing, *optional], day),
    )


def _frozen_changes(
    ctx: ReadContext, days: Sequence[date]
) -> dict[date, dict[tuple[str, str, str], tuple[int | None, int | None]]]:
    """For each of ``days`` with a ``results/screen_runs`` partition, the ``(new, dropped)``
    counts its newest run of each (owner, config) froze, keyed with the run id (a record of
    another run of the session never takes them): one small row per run, once per publish
    (ADR 0022). A session without the partition has none (the counts were not stored)."""
    key = (
        "recent_runs_changes",
        days[0],
        days[-1],
        ctx.reader.own_run,
        ctx.reader.version(),
        ctx.reader.runs_generation(),
    )

    def build() -> dict[date, dict[tuple[str, str, str], tuple[int | None, int | None]]]:
        out: dict[date, dict[tuple[str, str, str], tuple[int | None, int | None]]] = {}
        for day in days:
            if not ctx.reader.has_partition(SCREEN_RUNS, day):
                continue
            rows = ctx.reader.read_latest_runs(SCREEN_RUNS, day, columns=("new_picks", "dropped"))
            if rows is None:
                continue
            out[day] = {
                (str(u), str(c), str(r)): (_int(n), _int(d))
                for u, c, r, n, d in zip(
                    rows["user_id"],
                    rows["config_id"],
                    rows["run_id"],
                    rows["new_picks"],
                    rows["dropped"],
                    strict=True,
                )
            }
        return out

    found: dict[date, dict[tuple[str, str, str], tuple[int | None, int | None]]]
    found = ctx.cache.get_or_compute(key, build)
    return found


def load_recent_runs(
    ctx: ReadContext, keys: Sequence[RunKey], limit: int = DEFAULT_LIMIT
) -> dict[RunKey, tuple[RecentRun, ...]]:
    """For each ``(owner, config id)`` of ``keys`` its ``RecentRun`` for each of the last
    ``limit`` (cut to ``1..MAX_LIMIT``) exchange sessions ending at the request's session, oldest
    first, one entry per session, never skipped."""
    days = sessions_ending(ctx.session.date, min(max(limit, 1), MAX_LIMIT))
    served = days[-1] == ctx.session.date
    today = load_latest_runs(ctx, keys) if served else {}
    earlier = [d for d in days if not (served and d == ctx.session.date)]
    jobs = {key: run_job_name(key[1], key[0]) for key in keys}
    latest: dict[tuple[str, date], RunRecord] = {}
    changes: dict[date, dict[tuple[str, str, str], tuple[int | None, int | None]]] = {}
    if earlier:
        records = screen_records(ctx, frozenset(jobs.values()), earlier[0], earlier[-1])
        for record in records:  # by start time: the session's latest record is the last
            latest[(record.job, record.session_date)] = record
        changes = _frozen_changes(ctx, earlier)
    out: dict[RunKey, tuple[RecentRun, ...]] = {}
    for key, job in jobs.items():
        entries: list[RecentRun] = []
        for day in days:
            if served and day == ctx.session.date:
                run = today[key].run
                entries.append(_not_run(key[1], day, True) if run is None else _served(ctx, run))
                continue
            entries.append(_earlier(ctx, key, day, latest.get((job, day)), changes.get(day, {})))
        out[key] = tuple(entries)
    return out


def _earlier(
    ctx: ReadContext,
    key: RunKey,
    day: date,
    record: RunRecord | None,
    frozen: Mapping[tuple[str, str, str], tuple[int | None, int | None]],
) -> RecentRun:
    """``key``'s entry for an earlier ``day``: its latest record, else ``NOT_RUN``; a record that
    finished no screen (still running, failed) is asked of ``latest_run`` there, as
    ``pick_history`` does, so rows a run did store are never read as no run."""
    if record is None:
        return _not_run(key[1], day, False)
    decisions = record_decisions(record)
    if decisions is not None:
        counts = frozen.get((key[0], key[1], record.run_id), (None, None))
        return _of_record(day, record, decisions, counts)
    run = latest_run(at_session(ctx, day), *key).run
    if run is None:
        return _not_run(key[1], day, False)
    changes = {c.change: c.count for c in load_change_summary(at_session(ctx, day), run).counts}
    return _of_run(run, False, (changes.get("new"), changes.get("dropped")))
