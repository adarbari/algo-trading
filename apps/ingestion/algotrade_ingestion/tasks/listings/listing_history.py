"""``instruments/listing_history``: every US stock and ETF a vendor ever listed, with its
dates (ADR 0018 amendment 2026-10-08, edges ED6), merged with Massive's delisted names (ADR 0087).

``algotrade-ingest run listing-history`` pulls Tiingo's supported-tickers file (one request),
reads the latest ``instruments/delisted_tickers`` snapshot (the run FAILS without one: the
universe would silently lose the delisted names) and writes one full snapshot for the session:
every Tiingo row (those outside the universe's scope carry ``scope_reason``) and every Massive
record, paired or on its own (``listing_merge``, which also says how a Massive-only record gets
a start date). In NO workflow until the owner has run it on the real file and read the result.

Ids, in the order of ``instrument_ids.assign_listing_ids``: (1) the previous snapshot's id on
the same row, never upgraded; (2) a ``symbol_history`` row overlapping the listing; (3)
``EQ:TIINGO:<permaTicker>`` through ``equity_id``; (4) a Massive composite FIGI through
``equity_id`` when it names one listing and no id holds it; (5) none, with ``no_id_reason``
(never ``EQ:<symbol>``). No FIGI is looked up here.

The ``perma_ticker`` of a Tiingo row in scope comes from Tiingo's fundamentals meta (``meta``
source, batches of ``BATCH`` tickers, asked only for the tickers of rows that no ``symbol_history``
row gave an id): ``match_perma`` fills it by a unique ticker + active / inactive match, otherwise
the row keeps none (stats ``perma_matched``, ``perma_no_meta``, ``perma_ambiguous``). Out-of-scope
rows are never asked. A batch Tiingo does not answer is counted (``meta_batches_failed``) and its
rows stay without an id; no answer at all fails the run. The meta of a Massive-only record is one
request per record that has candidates (``meta_record_requests``, ``meta_record_failed``). Without
a ``meta`` source no row gets a ``perma_ticker``.

Rows are stamped with their own ``source`` (``tiingo`` or ``massive``).
"""

from collections.abc import Sequence
from datetime import date

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.data.listings.delisted import read_delisted_tickers
from algotrade.data.listings.universe import TABLE
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, NoResponseError, TaskContext
from algotrade_ingestion.tasks.listings.listing_merge import TIINGO, merge_listings
from algotrade_ingestion.tasks.reference.instrument_ids import (
    ID_MAP,
    assign_listing_ids_counted,
    history_matches,
    match_perma_reasons,
)
from algotrade_sources.framework.base import FetchRequest, Source

TASK = "listing-history"
HISTORY = "instruments/symbol_history"
KEY = "supported_tickers"
META = "perma_meta"  # the key of the meta adapter's ``Normalized.parsed`` frame
BATCH = 100  # tickers per meta request
META_COLUMNS = [
    "ticker",
    "perma_ticker",
    "is_active",
    "name",
    "data_provider_perma_ticker",
    "is_adr",
]


class _RecordMeta:
    """The meta question of one Massive-only record (``listing_merge``'s ``ask_meta``): one
    request, its raw answer kept, ``None`` when Tiingo did not answer or there is no source."""

    def __init__(self, run: IngestRun, meta: Source | None, day: date) -> None:
        self.run, self.meta, self.day = run, meta, day
        self.asked = self.failed = 0

    def __call__(self, tickers: Sequence[str]) -> pd.DataFrame | None:
        if self.meta is None:
            return None
        self.asked += 1
        request = FetchRequest(",".join(tickers), session_date=self.day)
        try:
            normalized = self.run.fetch(self.meta, request, raw_key=f"record{self.asked:05d}__meta")
        except NoResponseError:
            self.failed += 1
            return None
        return None if normalized is None else normalized.parsed[META]


def _latest(ctx: TaskContext, table: str, session: date) -> pd.DataFrame | None:
    """The latest partition of ``table`` on or before ``session``, or ``None``."""
    days = [d for d in ctx.reader.dates(table) if d <= session]
    return ctx.reader.table(table, days[-1]) if days else None


def _with_perma(
    run: IngestRun, meta: Source, rows: pd.DataFrame, history: pd.DataFrame | None, day: date
) -> tuple[pd.DataFrame, dict[str, int]] | None:
    """``rows`` with ``perma_ticker`` (and Tiingo's ``is_adr`` and ``data_provider_perma_ticker``)
    filled for the Tiingo rows in scope that no ``symbol_history`` row gave an id, the reason of
    those left without, and the stats; ``None`` when Tiingo answered no batch at all."""
    mine = rows[rows["source"].eq(TIINGO) & rows["scope_reason"].isna()]
    need = ~history_matches(mine, history)
    tickers = sorted(set(mine.loc[need, "ticker"].astype(str)))
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
        frames or [pd.DataFrame(columns=META_COLUMNS)], ignore_index=True
    ).drop_duplicates(["ticker", "perma_ticker"])
    perma, why, stats = match_perma_reasons(mine, found, need)
    stats.update(meta_tickers=len(tickers), meta_batches=len(batches), meta_batches_failed=failed)
    out = rows.copy()
    out.loc[mine.index, "perma_ticker"] = perma
    out.loc[mine.index, "no_id_reason"] = why.where(why != "", None)
    by_perma = found.set_index(["ticker", "perma_ticker"])
    for index, ticker, code in zip(mine.index, mine["ticker"], perma, strict=True):
        if code and (ticker, code) in by_perma.index:
            row = by_perma.loc[(ticker, code)]
            out.loc[index, "is_adr"] = bool(row["is_adr"])
            out.loc[index, "data_provider_perma_ticker"] = row["data_provider_perma_ticker"] or None
    return out, stats


def ingest_listing_history(
    ctx: TaskContext, source: Source, session: date, meta: Source | None = None
) -> RunRecord:
    history = _latest(ctx, HISTORY, session)
    previous = _latest(ctx, TABLE, session)
    id_map = _latest(ctx, ID_MAP, session)
    mapped = set() if id_map is None else {str(i) for i in id_map["new_id"].dropna()}
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
        try:
            delisted, delisted_snapshot = read_delisted_tickers(run.reader)
        except MissingDataError as error:
            run.failed(f"no Massive delisted tickers to merge: {error}")
            return run.record
        asker = _RecordMeta(run, meta, session)
        rows, merge_stats = merge_listings(listings, delisted, asker)
        extra: dict[str, int] = {}
        if meta is not None:
            matched = _with_perma(run, meta, rows, history, session)
            if matched is None:
                run.failed("Tiingo's meta endpoint answered no batch")
                return run.record
            rows, extra = matched
        rows, id_stats = assign_listing_ids_counted(rows, history, previous, mapped)
        rows.insert(0, "ts", pd.Timestamp(session, tz="UTC"))
        stored = rows.drop(columns="source")
        run.write(TABLE, stored.astype(object).where(stored.notna(), None), rows["source"])
        in_scope = rows["scope_reason"].isna()
        run.stats.update(
            listings=len(rows),
            out_of_scope=int((~in_scope).sum()),
            with_id=int(rows["instrument_id"].notna().sum()),
            without_id=int((in_scope & rows["instrument_id"].isna()).sum()),
            delisted_snapshot=delisted_snapshot.isoformat(),
            meta_record_failed=asker.failed,
            **merge_stats,
            **id_stats,
            **extra,
            **(normalized.notes if normalized is not None else {}),
        )
    return run.record
