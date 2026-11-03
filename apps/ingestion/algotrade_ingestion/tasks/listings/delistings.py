"""``events/delisting``: why and how each delisted name left (ADR 0087 decisions 4 and 5).

``algotrade-ingest run delistings --date D`` reads the latest ``instruments/listing_history``
snapshot through ``data.listings`` and writes one FULL snapshot for ``D``: a row per instrument id
whose listings have all ended on or before ``D`` (``delisted_listings``: the vendor's last trading
day, the final exchange and type). In NO workflow; the owner runs it after ``filings --delisted``
(whose 8-K items and Form 25 give the reason) and the Tiingo tails (whose OTC prints give the
terminal close). It reads stored data only: no source, no network.

Per instrument: ``last_session`` is the last stored bar on or before the last trading day within
``BAR_LOOKBACK_DAYS`` (none: no row, counted ``no_last_bar``); ``reason`` / ``known_from`` come from
its stored filings (``delisting_reason``); ``terminal_close`` is the first stored close in the
``OTC_SESSIONS`` sessions after ``last_session`` (Tiingo lists a delisted company's OTC prints
under the same id: CRSP's rule), else the convention of ``data.listings.delistings.convention``.
Closes are split-adjusted as of the terminal session (``SessionBars``, the outcomes task's basis),
so the return is the one a holder had. ``knowledge_ts`` is the write time.

Acceptance: no listing history FAILS the run. Stats: rows by reason and by basis, ``no_last_bar``,
``no_filings`` (instruments with no stored filing at all: ``filings --delisted`` not run for them),
``no_cik``, ``unknown_share`` (ADR decision 6 (c) reads it), and the snapshot used.
"""

from collections import Counter
from collections.abc import Iterator, Sequence
from datetime import date, timedelta

import numpy as np
import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.core.time.calendar import sessions_between
from algotrade.data.events import ALL_TIME, read_events
from algotrade.data.listings.delistings import (
    BASES,
    OTC_CLOSE,
    OTC_SESSIONS,
    REASONS,
    TABLE,
    UNKNOWN,
    convention,
)
from algotrade.data.listings.universe import delisted_listings
from algotrade.data.prices import SessionBars, session_bars
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.tasks.listings.delisting_reason import judge

TASK = "delistings"
FILINGS = "events/filing"
SOURCE = "delistings"
FILING_COLUMNS = ["instrument_id", "ts", "form", "items", "accession"]  # absent when none stored
BAR_LOOKBACK_DAYS = 30  # a last bar further before the last trading day is not its last bar
CHUNK = 250  # instruments (sorted by last day) whose bars are read at once
AFTER_DAYS = 25  # calendar days after the last bar that hold OTC_SESSIONS sessions


def _chunks(frame: pd.DataFrame) -> Iterator[pd.DataFrame]:
    for i in range(0, len(frame), CHUNK):
        yield frame.iloc[i : i + CHUNK]


def _bars(ctx: TaskContext, chunk: pd.DataFrame) -> SessionBars:
    """The closes around the chunk's last days (an empty ``SessionBars`` when none are stored)."""
    first = min(chunk["last_day"]) - timedelta(BAR_LOOKBACK_DAYS)
    last = max(chunk["last_day"]) + timedelta(AFTER_DAYS)
    try:
        return session_bars(
            ctx.reader, first, last, [str(i) for i in chunk["instrument_id"]], columns=("close",)
        )
    except MissingDataError:
        return SessionBars.empty()


def _closes(bars: SessionBars) -> dict[str, pd.DataFrame]:
    frame = bars.frame[bars.frame["close"].notna()]
    return {str(i): rows for i, rows in frame.groupby("instrument_id", sort=False)}


def _adjust(bars: SessionBars, instrument: str, close: float, as_of: date) -> float:
    """``close`` (adjusted to the range end) as of ``as_of``: the later splits multiplied back."""
    splits = bars.splits
    later = splits[(splits["instrument_id"] == instrument) & (splits["ex_date"] > as_of)]
    return close * float(np.prod(later["ratio"].to_numpy(dtype=float)))


def _last_session(rows: pd.DataFrame | None, last_day: date) -> tuple[date, float] | None:
    """The last bar on or before ``last_day`` within the lookback: its session and close."""
    if rows is None:
        return None
    day = pd.to_datetime(rows["session_date"]).dt.date
    kept = rows[(day <= last_day) & (day >= last_day - timedelta(BAR_LOOKBACK_DAYS))]
    if kept.empty:
        return None
    row = kept.iloc[-1]
    return pd.Timestamp(row["session_date"]).date(), float(row["close"])


def _terminal(rows: pd.DataFrame | None, last_session: date) -> tuple[date, float] | None:
    """The first close in the ``OTC_SESSIONS`` sessions after ``last_session``."""
    if rows is None:
        return None
    start = last_session + timedelta(1)
    end = sessions_between(start, last_session + timedelta(AFTER_DAYS + 5))[OTC_SESSIONS - 1]
    day = pd.to_datetime(rows["session_date"]).dt.date
    kept = rows[(day > last_session) & (day <= end)]
    if kept.empty:
        return None
    row = kept.iloc[0]
    return pd.Timestamp(row["session_date"]).date(), float(row["close"])


def _row(
    listing: pd.Series, filings: pd.DataFrame, bars: SessionBars, rows: pd.DataFrame | None
) -> dict[str, object] | None:
    iid, last_day = str(listing["instrument_id"]), listing["last_day"]
    last = _last_session(rows, last_day)
    if last is None:
        return None
    last_session, raw_last = last
    verdict = judge(filings, last_session)
    otc = _terminal(rows, last_session)
    as_of = otc[0] if otc else last_session
    last_close = _adjust(bars, iid, raw_last, as_of)
    if otc:
        terminal_close = _adjust(bars, iid, otc[1], as_of)
        basis, ret = OTC_CLOSE, terminal_close / last_close - 1
    else:
        terminal_close = None
        basis, ret = convention(verdict.reason, listing["exchange"])
    return {
        "instrument_id": iid,
        "ts": pd.Timestamp(last_session, tz="UTC"),
        "known_from": verdict.known_from,
        "last_session": last_session,
        "last_close": last_close,
        "reason": verdict.reason,
        "reason_source": verdict.reason_source,
        "exchange": listing["exchange"],
        "security_type": listing["security_type"],
        "cik": listing["cik"],
        "terminal_close": terminal_close,
        "terminal_session": otc[0] if otc else None,
        "terminal_basis": basis,
        "delisting_return": ret,
    }


def build_rows(
    ctx: TaskContext, gone: pd.DataFrame, filings: pd.DataFrame
) -> tuple[list[dict[str, object]], int]:
    """The rows of every delisted instrument with a last bar, and how many had none."""
    by_id = {str(i): rows for i, rows in filings.groupby("instrument_id")}
    empty = filings.iloc[0:0]
    out: list[dict[str, object]] = []
    for chunk in _chunks(gone.sort_values(["last_day", "instrument_id"], kind="stable")):
        bars = _bars(ctx, chunk)
        closes = _closes(bars)
        for _, listing in chunk.iterrows():
            iid = str(listing["instrument_id"])
            row = _row(listing, by_id.get(iid, empty), bars, closes.get(iid))
            if row is not None:
                out.append(row)
    return out, len(gone) - len(out)


def _counts(values: Sequence[str], vocabulary: Sequence[str]) -> dict[str, int]:
    seen = Counter(values)
    return {v: seen.get(v, 0) for v in vocabulary}


def ingest_delistings(ctx: TaskContext, session: date) -> RunRecord:
    with IngestRun(ctx, TASK, session) as run:
        try:
            gone, snapshot = delisted_listings(ctx.reader, session)
        except MissingDataError as exc:
            run.failed(f"no listing history to read: {exc}")
            return run.record
        if snapshot > session:  # the table is current knowledge: a replay would read the future
            run.failed(f"listing history of {snapshot} was written after the session {session}")
            return run.record
        ids = sorted({str(i) for i in gone["instrument_id"]})
        filings = read_events(ctx.reader, FILINGS, *ALL_TIME, ids).frame.reindex(
            columns=FILING_COLUMNS
        )
        rows, no_last_bar = build_rows(ctx, gone, filings)
        frame = pd.DataFrame(rows)
        if frame.empty:  # never leave an older snapshot as the latest silently
            run.failed("no delisting row: nothing delisted by the session, or no last bar stored")
        else:
            run.write(TABLE, frame, SOURCE)
        unknown = int((frame["reason"] == UNKNOWN).sum()) if len(frame) else 0
        with_filings = set(filings["instrument_id"].astype(str)) if len(filings) else set()
        run.stats.update(
            listing_snapshot=snapshot.isoformat(),
            delisted=len(gone),
            rows=len(frame),
            no_last_bar=no_last_bar,
            no_filings=sum(1 for i in ids if i not in with_filings),
            no_cik=int(gone["cik"].isna().sum()),
            by_reason=_counts(list(frame["reason"]) if len(frame) else [], REASONS),
            by_basis=_counts(list(frame["terminal_basis"]) if len(frame) else [], BASES),
            unknown_share=round(unknown / len(frame), 4) if len(frame) else None,
        )
    return run.record
