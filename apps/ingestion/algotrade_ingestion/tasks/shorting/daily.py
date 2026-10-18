"""The one loop of the FINRA tasks: one source request per date, resolved to ids, one partition
a date.

Each date is an item (``YYYY-MM-DD``). A date already stored is skipped (the partition is the
event date, so the skip needs no read of the rows) unless ``force``; FINRA keeps only the latest
revision of a short-interest date, so a stored date is never refetched in a normal run and the
first-seen value stays the point-in-time one. A date FINRA holds nothing for (a weekend, an
unpublished date, a date beyond the API's history) is ``NO_DATA``, not a failure, and is asked
again by the next run that covers it. Tickers the session's reference does not know are dropped
and counted (``stats["unresolved"]``): the tables hold the universe's names only.

A backfill is the same loop over a wider window (``--from``): it checkpoints after every date, so
an interrupted run is repeated and continues where the stored partitions end.
"""

from collections.abc import Callable, Mapping, Sequence
from datetime import date
from functools import partial

from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, NoResponseError, TaskContext
from algotrade_sources.framework.base import FetchRequest, Source

NO_DATA = "NO_DATA"


type Known = Callable[[date], Mapping[str, date]]  # a date -> its ``known_from`` (and kin)


def one_day(run: IngestRun, source: Source, table: str, known: Known, day: date) -> str:
    """Fetch, resolve and write one date's partition; the item status. ``known`` gives the
    columns the point-in-time rule adds (``schedule.py``: the task decides ``known_from``)."""
    try:
        normalized = run.fetch(source, FetchRequest(day.isoformat(), session_date=run.session))
    except NoResponseError:
        return NO_DATA
    frame = normalized.tables[table] if normalized else None
    if frame is None or frame.empty:
        return NO_DATA
    resolver = run.resolver()
    known_names = frame["symbol"].map(resolver.knows)
    run.unresolved += int((~known_names).sum())  # a ticker the reference does not know is dropped
    resolved = run.resolve(frame[known_names], keep_symbol=False)
    if resolved.empty:
        return f"{NO_DATA}: no ticker resolved"
    rows = resolved.reset_index(drop=True).assign(**known(day))
    run.write(table, rows, source.name, session=day)
    return f"OK: {len(resolved)} rows"


def store_days(
    ctx: TaskContext,
    task: str,
    table: str,
    source: Source,
    known: Known,
    days: Sequence[date],
    session: date,
    force: bool = False,
) -> RunRecord:
    """Store the partition of every date in ``days`` not already stored."""
    stored = set() if force else set(ctx.reader.dates(table))
    asked = [d for d in days if d not in stored]
    with IngestRun(ctx, task, session) as run:
        for day in asked:
            run.attempt(day.isoformat(), partial(one_day, run, source, table, known, day))
            run.checkpoint()
        run.stats.update(
            window=[days[0].isoformat(), days[-1].isoformat()] if days else [],
            dates=len(days),
            already_stored=len(days) - len(asked),
            counts=run.counts(),
        )
    return run.record
