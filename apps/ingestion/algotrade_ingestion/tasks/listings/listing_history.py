"""``instruments/listing_history``: every US stock and ETF a vendor ever listed, with its
dates (ADR 0018 amendment 2026-10-08, edges ED6).

``algotrade-ingest run listing-history`` pulls Tiingo's supported-tickers file (one request)
and writes it as a full snapshot for the session. In NO workflow until the owner has run it on
the real file and read the result (the adapter is tested on a recorded slice of the 2026-10-08
file).

Ids, in the amendment's order: (a) the listing's ticker and dates overlap an
``instruments/symbol_history`` row: that row's ``instrument_id``; (b) else, once the listing
has a ``perma_ticker`` (the meta pull, a later task), ``EQ:TIINGO:<permaTicker>`` through
``equity_id``; (c) never ``EQ:<symbol>``: the listing has no id (null) and is not used until
it gets one. No FIGI is looked up here.
"""

from datetime import date

import pandas as pd

from algotrade.data.listings.universe import TABLE
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, NoResponseError, TaskContext
from algotrade_ingestion.tasks.reference.instrument_ids import assign_listing_ids
from algotrade_sources.framework.base import FetchRequest, Source

TASK = "listing-history"
HISTORY = "instruments/symbol_history"
KEY = "supported_tickers"


def ingest_listing_history(ctx: TaskContext, source: Source, session: date) -> RunRecord:
    days = [d for d in ctx.reader.dates(HISTORY) if d <= session]
    history = ctx.reader.table(HISTORY, days[-1]) if days else None
    with IngestRun(ctx, TASK, session) as run:
        try:
            normalized = run.fetch(source, FetchRequest(KEY, session_date=session))
        except NoResponseError as error:
            run.failed(str(error))
            return run.record
        listings = None if normalized is None else normalized.parsed.get(TABLE)
        if listings is None or listings.empty:
            run.failed("the supported-tickers file held no usable listing")
            return run.record
        rows = assign_listing_ids(listings, history)
        rows.insert(0, "ts", pd.Timestamp(session, tz="UTC"))
        rows = rows.astype(object).where(rows.notna(), None)
        run.write(TABLE, rows, source.name)
        run.stats.update(
            listings=len(rows),
            with_id=int(rows["instrument_id"].notna().sum()),
            without_id=int(rows["instrument_id"].isna().sum()),
            **(normalized.notes if normalized is not None else {}),
        )
    return run.record
