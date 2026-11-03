"""``instruments/delisted_details``: Massive's ticker details at a delisted record's last day,
for the start its record still lacks (ADR 0087, PR3b).

``algotrade-ingest run delisted-details [--limit N]`` reads the latest
``instruments/listing_history`` snapshot, takes the rows of ``source = massive`` in scope with
no ``start_date``, an ``end_date`` and a ``no_id_reason`` that more data can lift (``no_start``,
``perma_ambiguous``, ``no_meta``; never ``pair_ambiguous`` or ``overlaps_listing``), minus the
(ticker, ``end_date``) already stored, and asks ``MassiveTickerDetails`` for each at
``date = end_date``: the company as it was then, whose ``list_date`` is the start (``listing_merge``
decides whether it is taken). In NO workflow.

Order: ``COMMON_STOCK`` and ``ADR`` first (the names the universe can hold), then no type, then the
rest; newest ``end_date`` first. At most ``limit`` are asked per run (none: all).

Runs are increments (``runs="merge"``): only the rows asked this run are written, the reader
(``data.listings.delisted.read_delisted_details``) takes the union. A name Massive does not know
that day (404) is stored as a marker (``found`` false) and never asked again. A request that fails
(network, rate limit) is a ``FETCH_ERROR`` item, stored nowhere and asked again by the next run; the
run FAILS only when every request failed. The run is resumable: a name fetched in an unfinished run
is not asked again, and the record is checkpointed every ``CHECKPOINT_EVERY`` requests.

Stats: ``asked`` (requests answered or failed, resumed ones included), ``found``, ``not_found``,
``failed``, ``remaining`` (due names not asked after this run). Time: the free tier answers one
request per 12.5 s (``[massive] min_interval_s``), so the whole list takes ``N x 12.5 s`` where
``N`` is the due count (``due`` in the stats): 1,000 names 3.5 h, 5,000 names 17.4 h; run long
lists detached (README "Long runs") and in slices with ``--limit``.
"""

from datetime import date
from functools import partial
from typing import Any

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.data.listings.delisted import DETAILS_TABLE, read_delisted_details
from algotrade.data.listings.universe import listing_frame
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, NoResponseError, TaskContext
from algotrade_sources.framework.base import FetchRequest, Source

TASK = "delisted-details"
TABLE = DETAILS_TABLE
REASONS = ("no_start", "perma_ambiguous", "no_meta")  # a start can lift these (listing_merge)
STOCK_TYPES = ("COMMON_STOCK", "ADR")
CHECKPOINT_EVERY = 25
FOUND, NOT_FOUND = "OK", "NOT_FOUND"
MASSIVE = "massive"
# What the source parsed (``vendors/massive/details.COLUMNS``; a task never imports a vendor, R3).
ANSWER = [
    "ticker", "list_date", "name", "cik", "figi", "share_class_figi", "vendor_type", "exchange",
    "active", "delisted_date", "market", "locale", "currency_name", "last_updated_utc",
    "sic_code", "sic_description", "homepage_url", "total_employees", "description",
]  # fmt: skip
COLUMNS = ["ts", "end_date", "asked_date", "found", *ANSWER]


def due_records(listings: pd.DataFrame, stored: pd.DataFrame) -> list[tuple[str, date]]:
    """The (ticker, last day) to ask, in asking order: the Massive-only rows still undated for a
    reason details can lift, not stored yet; stock types, then no type, then the rest; newest
    first."""
    rows = listings[
        listings["source"].eq(MASSIVE)
        & listings["start_date"].isna()
        & listings["end_date"].notna()
        & listings["no_id_reason"].isin(REASONS)
    ]
    have: set[tuple[str, date]] = set()
    if not stored.empty:
        have = set(zip(stored["ticker"], pd.to_datetime(stored["end_date"]).dt.date, strict=True))
    kind = rows["security_type"]
    rank = pd.Series(2, index=rows.index).mask(kind.isin(STOCK_TYPES), 0).mask(kind.isna(), 1)
    ended = pd.to_datetime(rows["end_date"]).dt.date
    ordered = (
        rows.assign(_rank=rank, _end=ended)
        .sort_values(["_rank", "_end", "ticker"], ascending=[True, False, True], kind="stable")
        .drop_duplicates(["ticker", "_end"])
    )
    return [(str(t), e) for t, e in zip(ordered["ticker"], ordered["_end"], strict=True)
            if (t, e) not in have]  # fmt: skip


def item_key(ticker: str, end: date) -> str:
    return f"{ticker}__{end.isoformat()}"


def request_key(ticker: str, end: date) -> str:
    """The request key of ``MassiveTickerDetails``: ``TICKER|YYYY-MM-DD``."""
    return f"{ticker}|{end.isoformat()}"


def _row(found: pd.Series | None, ticker: str, end: date, asked: date, ts: pd.Timestamp) -> Any:
    """One stored row: the answer's fields, or the marker (``found`` false) with none."""
    row: dict[str, Any] = dict.fromkeys(COLUMNS)
    if found is not None:
        row.update({c: found[c] for c in ANSWER})
    row.update(ts=ts, ticker=ticker, end_date=end, asked_date=asked, found=found is not None)
    return pd.DataFrame([row], columns=COLUMNS).astype(object)


def _ask(run: IngestRun, source: Source, ticker: str, end: date, ts: pd.Timestamp) -> str:
    request = FetchRequest(request_key(ticker, end), session_date=end)
    try:
        normalized = run.fetch(source, request, raw_key=item_key(ticker, end))
    except NoResponseError:
        found = None  # Massive does not know the ticker that day: a marker
    else:
        found = None if normalized is None else normalized.parsed["details"].iloc[0]
    run.stage(TABLE, item_key(ticker, end), _row(found, ticker, end, run.session, ts), MASSIVE)
    return NOT_FOUND if found is None else FOUND


def ingest_delisted_details(
    ctx: TaskContext, source: Source, session: date, limit: int | None = None
) -> RunRecord:
    ts = pd.Timestamp(session, tz="UTC")
    with IngestRun(ctx, TASK, session, resume=True) as run:
        try:
            listings, snapshot = listing_frame(ctx.reader)
        except MissingDataError as error:
            run.failed(f"no listing history to date: {error}")
            return run.record
        due = due_records(listings, read_delisted_details(ctx.reader))
        todo = due if limit is None else due[: max(limit, 0)]
        for ticker, end in todo:
            key = item_key(ticker, end)
            if key in run.items:
                continue  # fetched before a resume
            run.attempt(key, partial(_ask, run, source, ticker, end, ts))
            if len(run.items) % CHECKPOINT_EVERY == 0:
                run.checkpoint()
        counts = run.counts()
        asked = sum(counts.values())
        if asked and counts.get("FETCH_ERROR", 0) == asked:
            run.failed("every details request failed")
        rows = run.publish(TABLE, sort_by="ticker")
        failed = run.failures()
        done = sum(
            1
            for t, e in due
            if (status := run.items.get(item_key(t, e))) and not status.startswith("FETCH_ERROR")
        )
        run.stats.update(
            asked=asked, found=counts.get(FOUND, 0), not_found=counts.get(NOT_FOUND, 0),
            failed=counts.get("FETCH_ERROR", 0), failed_items=failed[:20],
            remaining=len(due) - done,
            due=len(due), rows=rows, listing_snapshot=snapshot.snapshot_date.isoformat(),
        )  # fmt: skip
    return run.record
