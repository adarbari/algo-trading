"""The ``option-history-import`` task (ADR 0084): a folder of bought HistoricalOptionData zips into
the option-history store (``ALGOTRADE_OPTION_HISTORY_URL``, its own root on the external drive).

``algotrade-ingest run option-history-import --source-dir <folder> [--from D] [--to D] [--limit N]
[--dry-run] [--force]``; ``--init`` first marks a new drive (its sentinel, a lock and rename probe).

- One committed run per session (``option-history-session``, a bad day fails its own item, never
  thousands of sessions): the quotes of every underlying, the underlyings' day and the vendor's
  option statistics, sorted by symbol, expiry and strike, stamped by ``IngestRun``
  (``session_date`` = the file's day, ``knowledge_ts`` = the write instant). The batch record
  (``option-history-import``) holds one item per session.
- Resumable: a session whose published run holds the same zip-member checksum is skipped; a changed
  checksum (or ``--force``) is a newer run. Where a daily and a monthly zip hold one session the
  later-named zip wins (the vendor adapter).
- Locks: the history store's own lock and ``recover_unpublished`` against it; the main ingest lock
  is never taken, so the nightly runs beside a multi-hour import. The CLI takes no lock for it.
- Ids: ``underlying_id`` is the index id for an index underlying (the adapter) and else the strict
  listing resolver's id as of the session (``data.listings``): a symbol with no listing then stays
  null and is counted, never ``EQ:<symbol>``. The listing history is in the MAIN store (the reader).
- The task SUCCEEDS or FAILS: a session that is not an exchange session, an empty or mixed-day
  options file, no ``stockquotes``, a duplicate contract, or no session found / imported while
  files existed fails it (the batch is FAILED, the sessions imported before it stay).
- The vendor's dividends and splits (``stockhistory`` zip) are stored once (``--force`` again):
  partition = ex-date, runs merge. They never enter ``events/dividend`` / ``events/split``.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date
from typing import Any, cast

import pandas as pd

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import is_session
from algotrade.data.listings.resolvers import listing_resolver
from algotrade.data.option_history.reading import SESSION_TASK
from algotrade.data.option_history.store import init_root, open_history
from algotrade.data.resolver import SymbolResolver
from algotrade.services.jobs.exclusive import exclusive_run
from algotrade.storage.runs import RunRecord, RunStatus, published, start_run
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext, recover_unpublished
from algotrade_sources.framework.base import HistoryFileSource, HistorySession

TASK = "option-history-import"
ACTIONS_TASK = "option-history-actions"
SOURCE = "historicaloptiondata"
QUOTES = "option_history/quotes"
UNDERLYING = "option_history/underlying"
STATS = "option_history/stats"
DIVIDENDS = "option_history/dividends"
SPLITS = "option_history/splits"
SORT = ["symbol", "expiry", "strike"]


@dataclass(frozen=True)
class ImportOptions:
    url: str | None = None  # the history store (default: ALGOTRADE_OPTION_HISTORY_URL)
    start: date | None = None
    end: date | None = None
    limit: int | None = None
    dry_run: bool = False
    force: bool = False
    init: bool = False


def fill_underlying_ids(frame: pd.DataFrame, resolver: SymbolResolver) -> tuple[pd.DataFrame, int]:
    """Null ``underlying_id`` filled from the listings alive on the session -> (frame, distinct
    symbols with no id). An id already there (an index) is kept; an unknown symbol stays null."""
    out = frame.copy()
    missing = out["underlying_id"].isna()
    if missing.any():
        found = out.loc[missing, "symbol"].map(lambda s: resolver.ids.get(str(s).strip().upper()))
        out.loc[missing, "underlying_id"] = found
    unresolved = out.loc[out["underlying_id"].isna(), "symbol"].nunique()
    return out, int(unresolved)


def held_checksums(writer: StoreWriter, session: date) -> set[str]:
    """The checksums of the published runs of ``session`` (a re-import with one is a no-op)."""
    return {
        str(r.stats["checksum"])
        for r in writer.runs_for(SESSION_TASK, session)
        if published(r) and "checksum" in r.stats
    }


def import_session(
    ctx: TaskContext,
    source: HistoryFileSource,
    entry: HistorySession,
    resolver: SymbolResolver,
    dry_run: bool,
) -> dict[str, Any]:
    """Read, check and (unless ``dry_run``) store one session as its own committed run -> the
    session's counts. Raises on any condition that fails the item."""
    day = entry.session
    if not is_session(day):
        raise ValueError(f"{day} is not an exchange session")
    bundle = source.read(day)
    if UNDERLYING not in bundle.tables:
        raise ValueError(f"{day}: no stockquotes file beside the options")
    quotes, unresolved = fill_underlying_ids(bundle.tables[QUOTES], resolver)
    quotes = quotes.sort_values(SORT, kind="stable").reset_index(drop=True)
    stats: dict[str, Any] = {
        **bundle.notes,
        "checksum": entry.checksum,
        "zip": entry.location,
        "complete_files": entry.complete,
        "unresolved_symbols": unresolved,
        # the ten most frequent excluded roots with their rows (a pre-2010 index root shows)
        "nonstandard_roots": ", ".join(
            f"{r.root}:{r.rows}" for r in bundle.parsed["excluded_roots"].itertuples()
        ),
        "null_underlying_rows": int(quotes["underlying_id"].isna().sum()),
    }
    if dry_run:
        return stats
    frames = {QUOTES: quotes}
    for table in (UNDERLYING, STATS):
        if table in bundle.tables:
            filled, _ = fill_underlying_ids(bundle.tables[table], resolver)
            frames[table] = filled.sort_values("symbol", kind="stable").reset_index(drop=True)
    with IngestRun(ctx, SESSION_TASK, day) as run:
        run.stats.update(stats)
        for table, frame in frames.items():
            run.write(table, frame, SOURCE, session=day)
    return stats


def import_actions(ctx: TaskContext, source: HistoryFileSource, today: date, force: bool) -> int:
    """Store the vendor's dividends and splits (partition = ex-date) once; -> rows stored."""
    if not force and any(published(r) for r in ctx.writer.runs_for(ACTIONS_TASK)):
        return 0
    history = source.stock_history()
    if history is None:
        return 0
    rows = 0
    with IngestRun(ctx, ACTIONS_TASK, today) as run:
        for table, frame in history.tables.items():
            for ex_date, part in frame.groupby("ex_date", sort=True):
                run.write(table, part.reset_index(drop=True), SOURCE, session=cast(date, ex_date))
                rows += len(part)
        run.stats["rows"] = rows
    return rows


def _initialised(ctx: TaskContext, today: date, url: str | None) -> RunRecord:
    path = init_root(url)
    record = start_run(TASK, today, ctx.clock())
    record.status, record.finished_at = RunStatus.COMPLETE, ctx.clock()
    record.stats["initialised"] = str(path)
    return record


def import_history(
    ctx: TaskContext,
    today: date,
    options: ImportOptions,
    open_store: Callable[[str | None], Any] = open_history,
) -> RunRecord:
    """The batch: list the folder's sessions, import the ones not already held, store the stock
    history, FAIL by the acceptance rules. ``ctx.reader`` is the MAIN store (the listings)."""
    if options.init:
        return _initialised(ctx, today, options.url)
    source = ctx.sources.get("hod_files")
    if not isinstance(source, HistoryFileSource):
        raise ConfigurationError("option-history-import needs --source-dir (the folder of zips)")
    backend = open_store(options.url)
    writer = StoreWriter(backend)
    hctx = replace(ctx, writer=writer, reader=ctx.reader)
    with exclusive_run(backend, wait=False):
        recover_unpublished(writer, ctx.clock())
        return _batch(hctx, source, today, options)


def _batch(
    ctx: TaskContext,
    source: HistoryFileSource,
    today: date,
    options: ImportOptions,
) -> RunRecord:
    found = [
        s
        for s in source.sessions()
        if (options.start is None or s.session >= options.start)
        and (options.end is None or s.session <= options.end)
    ]
    resolver_on = listing_resolver(ctx.reader)
    with IngestRun(ctx, TASK, today) as batch:
        batch.stats.update(sessions_found=len(found), dry_run=options.dry_run)
        if not found:
            batch.failed("no session found under the source folder in the requested range")
            return batch.record
        todo = [
            s
            for s in found
            if options.force or s.checksum not in held_checksums(ctx.writer, s.session)
        ]
        batch.stats["already_held"] = len(found) - len(todo)
        if options.limit is not None:
            todo = todo[: options.limit]
        failed: list[str] = []
        totals = {"rows": 0, "zero_bid": 0, "crossed": 0, "null_underlying_rows": 0}
        for entry in todo:
            key = entry.session.isoformat()
            try:
                counts = import_session(
                    ctx, source, entry, resolver_on(entry.session), options.dry_run
                )
            except Exception as exc:
                batch.fail(key, f"{type(exc).__name__}: {exc}")
                failed.append(key)
                continue
            batch.record_item(key, "OK")
            for name in totals:
                totals[name] += int(counts.get(name, 0))
            batch.checkpoint()
        done = "parsed" if options.dry_run else "imported"  # a dry run stores nothing
        batch.stats.update({done: len(todo) - len(failed), "failed": len(failed), **totals})
        if failed:
            batch.failed(f"{len(failed)} sessions failed: {', '.join(failed[:5])}")
        elif todo and not options.dry_run:
            batch.stats["actions_rows"] = import_actions(ctx, source, today, options.force)
    return batch.record
