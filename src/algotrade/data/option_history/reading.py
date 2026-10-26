"""Reads of the option-history tables (ADR 0086), by session and underlying symbol.

A session's rows are the partition's latest published run's, found from the import's run
records. ``symbol`` (the vendor's underlying symbol) is what a read filters on, because
``underlying_id`` is null where no listing id covered the session; the quotes file is clustered
by ``symbol``, so a read of a few names decodes few row groups.
"""

from collections.abc import Collection
from datetime import date

import pandas as pd

from algotrade.storage.runs import published
from algotrade.storage.tables.interfaces import RowFilter
from algotrade.storage.tables.readers import StoreReader

QUOTES = "option_history/quotes"
UNDERLYING = "option_history/underlying"
STATS = "option_history/stats"
DIVIDENDS = "option_history/dividends"
SPLITS = "option_history/splits"
SESSION_TASK = "option-history-session"  # the per-session import run (tasks/options_history)


def session_run(reader: StoreReader, session: date) -> str | None:
    """The run id of the latest published import of ``session``, or ``None``."""
    runs = [r for r in reader.runs(SESSION_TASK, session) if published(r)]
    return max(runs, key=lambda r: (r.started_at, r.run_id)).run_id if runs else None


def _read(
    reader: StoreReader, table: str, session: date, symbols: Collection[str] | None
) -> pd.DataFrame | None:
    run_id = session_run(reader, session)
    if run_id is None:
        return None
    where = (RowFilter("symbol", frozenset(s.upper() for s in symbols)),) if symbols else ()
    return reader.read_run(table, session, run_id, where=where)


def option_quotes(
    reader: StoreReader, session: date, symbols: Collection[str] | None = None
) -> pd.DataFrame | None:
    """The contracts of ``symbols`` (``None``: every underlying) quoted on ``session``."""
    return _read(reader, QUOTES, session, symbols)


def underlying_quotes(
    reader: StoreReader, session: date, symbols: Collection[str] | None = None
) -> pd.DataFrame | None:
    """The underlyings' day (OHLCV) on ``session``."""
    return _read(reader, UNDERLYING, session, symbols)


def option_stats(
    reader: StoreReader, session: date, symbols: Collection[str] | None = None
) -> pd.DataFrame | None:
    """The vendor's 30-day IV and the volume and open interest by side on ``session``."""
    return _read(reader, STATS, session, symbols)


def sessions(reader: StoreReader) -> list[date]:
    """The sessions with option quotes stored (every run, published or not: a partition)."""
    return reader.dates(QUOTES)
