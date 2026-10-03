"""Daily bars and corporate actions from Massive.

``ingest_daily_bars``: one ``bars/1d`` partition per session date, unadjusted. Dates already
stored are skipped unless forced, so a 2-year backfill (~500 requests at 5/minute, ~1h45m) can
be interrupted and resumed. Holidays return no rows and are recorded, not treated as errors.

``ingest_corporate_actions``: splits and dividends in a date window, stored as point-in-time
snapshots in ``events/split`` and ``events/dividend`` (partition = the run's session).
"""

from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta

from algotrade.storage.readers import StoreReader
from algotrade.storage.runs import RunRecord, RunStatus, new_run_id
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.jobs.common import stamp
from algotrade_ingestion.sources.base import FetchRequest, Source

BARS = "bars/1d"
CHECKPOINT_EVERY = 5


def sessions_between(start: date, end: date) -> list[date]:
    """Weekdays in ``[start, end]``; exchange holidays come back empty and are recorded."""
    return [
        start + timedelta(i)
        for i in range((end - start).days + 1)
        if (start + timedelta(i)).weekday() < 5
    ]


def _one_session(
    writer: StoreWriter, source: Source, day: date, run: RunRecord, clock: Callable[[], datetime]
) -> str:
    request = FetchRequest(day.isoformat(), session_date=day)
    payload = source.fetch(request)
    if payload is None:
        return "FETCH_ERROR: no response"
    writer.raw.put(source.name, source.dataset, day, run.run_id, day.isoformat(), payload)
    normalized = source.normalize(request, payload)
    bars = normalized.tables[BARS] if normalized else None
    if bars is None or bars.empty:
        return "NO_SESSION"
    now = clock()
    writer.write_table(BARS, day, run.run_id, stamp(bars, day, now, source.name, run.run_id))
    invalid = normalized.notes.get("invalid_rows", 0) if normalized else 0
    return f"OK: {len(bars)} bars" + (f", {invalid} invalid dropped" if invalid else "")


def ingest_daily_bars(
    writer: StoreWriter,
    reader: StoreReader,
    source: Source,
    sessions: Sequence[date],
    force: bool = False,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RunRecord:
    now = clock()
    last = max(sessions)
    run = RunRecord(new_run_id("daily_bars", last, now), "daily_bars", last, now)
    stored = set(reader.dates(BARS))
    for i, day in enumerate(sorted(sessions), start=1):
        if day in stored and not force:
            run.items[day.isoformat()] = "STORED"
            continue
        try:
            run.items[day.isoformat()] = _one_session(writer, source, day, run, clock)
        except Exception as exc:
            run.items[day.isoformat()] = f"FETCH_ERROR: {exc}"
        if i % CHECKPOINT_EVERY == 0:
            writer.save_run(run)
    counts: dict[str, int] = {}
    for status in run.items.values():
        counts[status.split(":")[0]] = counts.get(status.split(":")[0], 0) + 1
    run.status = RunStatus.PARTIAL if counts.get("FETCH_ERROR") else RunStatus.COMPLETE
    run.finished_at, run.stats = clock(), {"sessions": counts}
    writer.save_run(run)
    return run


def ingest_corporate_actions(
    writer: StoreWriter,
    source: Source,
    session: date,
    start: date,
    end: date,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RunRecord:
    now = clock()
    run_id = new_run_id("corporate_actions", session, now)
    stats: dict[str, object] = {"window": [start.isoformat(), end.isoformat()]}
    failed = []
    for kind in ("splits", "dividends"):
        request = FetchRequest(
            f"{kind}:{start.isoformat()}:{end.isoformat()}", session_date=session
        )
        try:
            payload = source.fetch(request)
            if payload is None:
                raise ValueError("no response")
            writer.raw.put(source.name, source.dataset, session, run_id, kind, payload)
            normalized = source.normalize(request, payload)
            for table, frame in normalized.tables.items() if normalized else []:
                stats[table] = len(frame)
                if not frame.empty:
                    writer.write_table(
                        table, session, run_id, stamp(frame, session, now, source.name, run_id)
                    )
        except Exception as exc:
            failed.append(f"{kind}: {exc}")
    stats["failed"] = failed
    record = RunRecord(
        run_id,
        "corporate_actions",
        session,
        now,
        RunStatus.PARTIAL if failed else RunStatus.COMPLETE,
        now,
        stats=stats,
    )
    writer.save_run(record)
    return record
