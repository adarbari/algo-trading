"""``instruments/listing_history``: every US stock and ETF a vendor ever listed, with its
dates (ADR 0018 amendment 2026-10-08, edges ED6).

``algotrade-ingest run listing-history`` pulls Tiingo's supported-tickers file (one request)
and writes it as a full snapshot for the session. In NO workflow until the owner has run it on
the real file and read the result (the adapter is tested on a recorded slice of the 2026-10-08
file).

Ids, in the amendment's order: (a) the listing's ticker and dates overlap an
``instruments/symbol_history`` row: that row's ``instrument_id``; (b) else, once the listing
has a ``perma_ticker``, ``EQ:TIINGO:<permaTicker>`` through ``equity_id``; (c) never
``EQ:<symbol>``: the listing has no id (null) and is not used until it gets one. No FIGI is
looked up here.

The ``perma_ticker`` comes from Tiingo's fundamentals meta (``meta`` source, batches of
``BATCH`` tickers, asked only for the tickers of listings that no ``symbol_history`` row gave an
id): ``match_perma`` fills it by a unique ticker + active / inactive match, otherwise the
listing keeps none (stats ``perma_matched``, ``perma_no_meta``, ``perma_ambiguous``). A batch
Tiingo does not answer is counted (``meta_batches_failed``) and its listings stay without an id;
no answer at all fails the run. Without a ``meta`` source the file's listings keep no
``perma_ticker``.
"""

from datetime import date

import pandas as pd

from algotrade.data.listings.universe import TABLE
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, NoResponseError, TaskContext
from algotrade_ingestion.tasks.reference.instrument_ids import assign_listing_ids, match_perma
from algotrade_sources.framework.base import FetchRequest, Source

TASK = "listing-history"
HISTORY = "instruments/symbol_history"
KEY = "supported_tickers"
META = "perma_meta"  # the key of the meta adapter's ``Normalized.parsed`` frame
BATCH = 100  # tickers per meta request


def _with_perma(
    run: IngestRun, meta: Source, listings: pd.DataFrame, history: pd.DataFrame | None, day: date
) -> tuple[pd.DataFrame, dict[str, int]] | None:
    """``listings`` with ``perma_ticker`` filled for those without a ``symbol_history`` id, and
    the stats; ``None`` when Tiingo answered no batch at all."""
    need = assign_listing_ids(listings, history)["instrument_id"].isna()
    tickers = sorted(set(listings.loc[need, "ticker"].astype(str)))
    batches = [tickers[i : i + BATCH] for i in range(0, len(tickers), BATCH)]
    frames, failed = [], 0
    for batch in batches:
        try:
            normalized = run.fetch(
                meta, FetchRequest(",".join(batch), session_date=day), raw_key=f"{batch[0]}__meta"
            )
        except NoResponseError:
            failed += 1
            continue
        if normalized is not None:
            frames.append(normalized.parsed[META])
    if batches and failed == len(batches):
        return None
    found = pd.concat(
        frames or [pd.DataFrame(columns=["ticker", "perma_ticker", "is_active"])],
        ignore_index=True,
    ).drop_duplicates(["ticker", "perma_ticker"])
    perma, stats = match_perma(listings, found, need)
    stats.update(meta_tickers=len(tickers), meta_batches=len(batches), meta_batches_failed=failed)
    return listings.assign(perma_ticker=perma), stats


def ingest_listing_history(
    ctx: TaskContext, source: Source, session: date, meta: Source | None = None
) -> RunRecord:
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
        extra: dict[str, int] = {}
        if meta is not None:
            matched = _with_perma(run, meta, listings, history, session)
            if matched is None:
                run.failed("Tiingo's meta endpoint answered no batch")
                return run.record
            listings, extra = matched
        rows = assign_listing_ids(listings, history)
        rows.insert(0, "ts", pd.Timestamp(session, tz="UTC"))
        rows = rows.astype(object).where(rows.notna(), None)
        run.write(TABLE, rows, source.name)
        run.stats.update(
            listings=len(rows),
            with_id=int(rows["instrument_id"].notna().sum()),
            without_id=int(rows["instrument_id"].isna().sum()),
            **extra,
            **(normalized.notes if normalized is not None else {}),
        )
    return run.record
