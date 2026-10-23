"""``analyst-backfill``: Yahoo's analyst data of the whole stock population, one batch a run
(ADR 0080 amendment 2026-10-23b).

The nightly Yahoo step takes ``[yahoo] per_night`` names, which would need weeks to reach the
~5,600 operating companies the universe holds. This task asks them in batches of ``[yahoo]
backfill_batch`` (500), each batch one run that commits and ends, so the ingest lock is released
between batches (the launchd nightly exits 3 while it is held) and a stopped backfill loses only
the batch in flight. It is driven by ``scripts/ops/yahoo_backfill.sh``, a loop the owner starts.

- the names are ``population.listed_names`` (the reference's COMMON_STOCK and ADR rows, whether or
  not FMP answers them or the scope list holds them), largest market cap first (``ordering.py``);
- a name is due when Yahoo never answered it and did not say it is unknown (404) within its hold
  (four ``[yahoo] refresh_days``); an answered name is the nightly step's from then on, so a
  re-run resumes where the last batch stopped, with no state of its own (``snapshot.history``
  reads this task's run items too);
- it does nothing, quietly (a COMPLETE record that is not saved, exit 0), until the nightly of the
  last closed session is complete, so a batch never delays the nightly it must follow;
- fail-soft, stricter than the nightly: the first HTTP 429 stops the batch (Yahoo is throttling,
  more calls only deepen the block), as do three failed calls in a row; calls are paced at
  ``[yahoo] backfill_min_interval_s`` (0.3 s; measured: 20 unpaced calls answered 200 in 0.9 s),
  the floor the registry builds the Yahoo source's limiter with for this task (``paced``: it
  doubles up to 3 s on errors and halves after 50 clean calls; the shared limiter, not a sleep
  here). Sequential: the limiter is shared across threads, but the run's staging is not built
  for concurrent workers, and 0.3 s a call already fits the target;
- stats say how it stands, for the loop: ``due_remaining`` (names still due after the batch),
  ``progress`` (names answered, 404 included), ``waiting`` (the nightly is not complete: nothing
  was asked) and ``stopped`` (why the batch ended early; ``rate_limited`` for a 429).

The rows are the nightly's (table, kinds, ``yahoo`` source and licence), staged by the same
``snapshot.ask_yahoo`` and published as one partition of the last closed session.
"""

import dataclasses
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any

from algotrade.config.site.settings import SourcesSettings
from algotrade.core.time.calendar import last_closed_session
from algotrade.storage.runs import RunRecord, RunStatus, done_sessions, start_run
from algotrade_ingestion.tasks.analyst import snapshot
from algotrade_ingestion.tasks.analyst.ordering import by_market_cap
from algotrade_ingestion.tasks.analyst.population import Name, listed_names
from algotrade_ingestion.tasks.framework import source_guards
from algotrade_ingestion.tasks.framework.run import FAILURES, IngestRun, TaskContext
from algotrade_sources.framework.base import Source

TASK = snapshot.BACKFILL_TASK
NIGHTLY = "nightly"  # the job name of the nightly workflow's per-session run records
SOURCES = (source_guards.YAHOO_SOURCE,)
SLOWEST_S = 3.0  # the pacing ceiling after repeated errors
CLEAN_CALLS = 50  # calls without an error that halve the interval again


def paced(settings: SourcesSettings) -> SourcesSettings:
    """``settings`` with the Yahoo source paced for the backfill: the floor ``[yahoo]
    backfill_min_interval_s`` (0.3 s; the nightly keeps ``min_interval_s``), a ceiling of
    ``SLOWEST_S``, and the shared limiter's adaptive rule tuned to double the interval when
    over ``max_error_rate`` of the last ``error_window`` calls erred (5xx, a block, a timeout)
    and halve it after ``CLEAN_CALLS`` calls without an error. What the registry builds this
    task's sources with (the limiter, shared by every process, enforces it)."""
    vendor = settings.vendor("yahoo")
    floor = settings.yahoo.backfill_min_interval_s
    adaptive = dataclasses.replace(
        vendor, min_interval_s=floor, max_interval_s=max(SLOWEST_S, floor), start_interval_s=None
    )
    return dataclasses.replace(
        settings,
        vendors={**settings.vendors, "yahoo": adaptive},
        http_backoff_factor=2.0,
        http_speedup_factor=2.0,
        http_speedup_after=CLEAN_CALLS,
    )


def run(ctx: TaskContext, params: Mapping[str, Any]) -> RunRecord:
    """The registry's entry: ``limit`` caps the batch below ``[yahoo] backfill_batch``."""
    return backfill(ctx, params.get("limit"))


def backfill(ctx: TaskContext, limit: Any = None) -> RunRecord:
    session = last_closed_session(ctx.clock(), timedelta(0))
    finished = done_sessions(ctx.reader.runs_of((NIGHTLY,), session, session))
    if session not in finished:
        return waiting(ctx, session)
    source = ctx.sources[source_guards.YAHOO_SOURCE]
    settings = ctx.settings.yahoo
    with IngestRun(ctx, TASK, session) as run_:
        started = run_.clock()
        names = {n.symbol: n for n in listed_names(run_.reader, session)}
        past = snapshot.history(run_)
        hold = timedelta(days=snapshot.RETRY_WINDOWS * settings.refresh_days)
        holding = {s for s, day in past.yahoo_refused.items() if session - day < hold}
        due = [s for s in names if s not in past.yahoo and s not in holding]
        ids = {s: names[s].instrument_id for s in due}
        due = by_market_cap(due, ids, snapshot.caps(run_))
        batch = (
            settings.backfill_batch if limit is None else min(settings.backfill_batch, int(limit))
        )
        out = ask_batch(run_, source, [names[s] for s in due[:batch]], started)
        answered = out.pop("answered")
        out.update(
            population=len(names),
            held_not_covered=len(holding),
            due=len(due),
            progress=answered,
            due_remaining=len(due) - answered,
        )
        run_.stats.update(out, licence={"yahoo": settings.licence})
        run_.stats.update(rows=run_.publish(snapshot.TABLE), counts=run_.counts())
    return run_.record


def waiting(ctx: TaskContext, session: date) -> RunRecord:
    """The quiet no-op: a COMPLETE record for the caller to print, saved nowhere (a loop asks every
    minute, and a record each would bury the real batches)."""
    record = start_run(TASK, session, ctx.clock())
    reason = f"the nightly of {session} is not complete: nothing asked, will not delay it"
    record.finish(ctx.clock(), stats={"waiting": reason, "due_remaining": None})
    assert record.status is RunStatus.COMPLETE
    return record


def ask_batch(
    run_: IngestRun, source: Source, take: list[Name], started: datetime
) -> dict[str, Any]:
    """Ask ``take`` in order; stop at the first 429, after three failures in a row or when
    ``[yahoo] run_budget_s`` is spent. Returns the batch's stats (``answered``: OK, EMPTY, 404)."""
    settings = run_.ctx.settings.yahoo
    labels: list[str] = []
    stopped, rate_limited, streak = "", False, 0
    for done, name in enumerate(take, 1):
        if snapshot.out_of_time(run_, started, settings.run_budget_s):
            stopped = "[yahoo] run_budget_s is spent"
            break
        errors: list[int] = []
        label = snapshot.ask_yahoo(run_, source, f"{snapshot.YAHOO}{name.symbol}", name, errors)
        snapshot.mark_coverage(run_, name, "yahoo", [label])
        labels.append(label)
        streak = streak + 1 if label in FAILURES else 0
        if snapshot.YAHOO_RATE_LIMITED in errors:
            stopped, rate_limited = snapshot.RATE_LIMITED_REASON, True
        elif streak >= snapshot.YAHOO_MAX_FAILURES:
            stopped = f"yahoo failed {snapshot.YAHOO_MAX_FAILURES} calls in a row"
        if stopped:
            break
        if done % snapshot.CHECKPOINT_EVERY == 0:
            run_.checkpoint()
    return {
        "asked": len(labels),
        "answered": sum(1 for x in labels if x not in FAILURES),
        "fetched": sum(1 for x in labels if x in (snapshot.OK, snapshot.EMPTY)),
        "not_covered": labels.count(snapshot.NOT_COVERED),
        "failed": sum(1 for x in labels if x in FAILURES),
        "stopped": stopped or None,
        "rate_limited": rate_limited,
    }
