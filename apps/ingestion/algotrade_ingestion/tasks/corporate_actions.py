"""Corporate actions (splits, dividends) as point-in-time event snapshots.

Each run fetches a date window (default: ``config/site/sources.toml`` ``[massive]``
``corporate_actions_window`` around the session) and writes ``events/split`` and
``events/dividend`` into the partition of the run's session. The source decides which
requests cover the window (``WindowedSource.window_requests``).
"""

from datetime import date
from functools import partial

from algotrade.storage.runs import RunRecord
from algotrade_ingestion.sources.base import FetchRequest, Source, WindowedSource
from algotrade_ingestion.tasks.framework import IngestRun, TaskContext

TASK = "corporate_actions"


def _one_request(run: IngestRun, source: Source, label: str, request: FetchRequest) -> str:
    normalized = run.fetch(source, request, raw_key=label)
    rows = 0
    for table, raw in normalized.tables.items() if normalized else []:
        frame = run.resolve(raw)
        run.stats[table] = len(frame)
        rows += len(frame)
        if not frame.empty:
            run.write(table, frame, source.name)
    return f"OK: {rows} rows"


def ingest_corporate_actions(
    ctx: TaskContext, source: Source, session: date, start: date, end: date
) -> RunRecord:
    if not isinstance(source, WindowedSource):
        raise TypeError(f"{source.name}: corporate actions need a WindowedSource")
    with IngestRun(ctx, TASK, session) as run:
        run.stats["window"] = [start.isoformat(), end.isoformat()]
        for label, request in source.window_requests(start, end, session):
            run.attempt(label, partial(_one_request, run, source, label, request))
        run.stats["failed"] = run.failures()
    return run.record
