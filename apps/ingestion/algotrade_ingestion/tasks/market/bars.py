"""Daily bars from Massive: one ``bars/1d`` partition per session date, unadjusted.

Dates already stored are skipped unless forced, so a 2-year backfill (~500 requests at
5/minute, ~1h45m) can be interrupted and resumed. Sessions come from the exchange calendar
(``core/time/calendar.py``); a session the vendor has no rows for is recorded, not an error.
Vendor tickers become ids through the reference as of each session (ADR 0018); the loop
itself (raw save, ids, stamping, run record) is ``IngestRun``'s.

Not published yet (ADR 0043): for the last closed session, a 403 or an empty answer is
NOT_PUBLISHED (not an error) only when the session before still answers 200, so the vendor
works and merely has not published the session; otherwise it stays a failure (an expired key
or plan). The ``bars_fresh`` check (``tasks/maintenance/quality.py``) reads that item and
marks its FAIL pending, which the nightly turns into WAITING until its deadline.
"""

from collections.abc import Sequence
from datetime import date, timedelta
from functools import partial
from typing import Protocol, runtime_checkable

from algotrade.core.time.calendar import last_closed_session, previous_session
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_sources.framework.base import FetchRequest, Source

TASK = "daily_bars"
BARS = "bars/1d"
CHECKPOINT_EVERY = 5
NOT_PUBLISHED = "NOT_PUBLISHED"  # the item status; ``quality.check_bars`` reads it
FORBIDDEN = 403


@runtime_checkable
class Probing(Protocol):
    def probe(self, day: date) -> int:
        """The HTTP status of one request for ``day`` (no retries)."""
        ...


def _unpublished(run: IngestRun, source: Source, day: date) -> bool:
    """Whether ``day`` (the last closed session) is merely not published yet: the session
    before it answers 200. Anything else (no probe, an error, another status) is not."""
    if not isinstance(source, Probing) or day < last_closed_session(run.clock(), timedelta(0)):
        return False
    try:
        return source.probe(previous_session(day)) == 200
    except Exception:  # a failed probe proves nothing: the failure stands
        return False


def _one_session(run: IngestRun, source: Source, day: date) -> str:
    request = FetchRequest(day.isoformat(), session_date=day)
    try:
        normalized = run.fetch(source, request)
    except RuntimeError as exc:  # a vendor that gave up carries its last HTTP ``status``
        if getattr(exc, "status", None) == FORBIDDEN and _unpublished(run, source, day):
            return f"{NOT_PUBLISHED}: HTTP {FORBIDDEN} while the session before answers 200"
        raise
    bars = normalized.tables[BARS] if normalized else None
    if bars is None or bars.empty:
        if _unpublished(run, source, day):
            return f"{NOT_PUBLISHED}: empty while the session before answers 200"
        return "NO_SESSION"
    before = run.unresolved
    bars = run.resolve(bars, as_of=day, keep_symbol=False)
    bars = bars.drop_duplicates("instrument_id", keep="last").sort_values("instrument_id")
    run.write(BARS, bars, source.name, session=day)
    invalid = normalized.notes.get("invalid_rows", 0) if normalized else 0
    unknown = run.unresolved - before
    notes = (f", {invalid} invalid dropped" if invalid else "") + (
        f", {unknown} unresolved" if unknown else ""
    )
    return f"OK: {len(bars)} bars{notes}"


def ingest_daily_bars(
    ctx: TaskContext, source: Source, sessions: Sequence[date], force: bool = False
) -> RunRecord:
    stored = set(ctx.reader.dates(BARS))
    with IngestRun(ctx, TASK, max(sessions)) as run:
        for i, day in enumerate(sorted(sessions), start=1):
            if day in stored and not force:
                run.record_item(day.isoformat(), "STORED")
                continue
            run.attempt(day.isoformat(), partial(_one_session, run, source, day))
            if i % CHECKPOINT_EVERY == 0:
                run.checkpoint()
        run.stats["sessions"] = run.counts()
    return run.record
