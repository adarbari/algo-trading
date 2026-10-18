"""Item sections of 10-K / 10-Q filings (``events/filing_text``) for consumers and the producer.

One row per instrument, filing (``accession``: a 10-K/A is its own filing), item and
``parser_version``; ``item`` is null on the one row of a filing no item header was found in.

**The read rule** (ADR 0007, ADR 0050 decision 3): as of session S a row is known when its
effective ``known_from`` is on or before S, the stored ``known_from`` floored by the acceptance
session recomputed from ``ts`` (``events.acceptance_sessions``), so a row can never be read before
its filing was public, whatever stamp it carries. Per (instrument, accession, item) the version
read is the latest known: highest ``known_from``, then ``parser_version``, then ``knowledge_ts``.
A later parser version that changed a text is known only from the day it ran (the producer
stamps it), so a read before that day sees the older text; one that did not change it carries
the older row's ``known_from``. The null-item row of a filing is dropped when the filing has an
item row (an earlier parser found nothing, a later one did), never the other way round: a later
parser that finds nothing does not erase items an earlier one found.

Rows carry ``quality`` (``OK``, ``SHORT``, ``TRUNCATED``, ``NOT_FOUND``, ``NO_ITEMS``); a text
read for a signal is an ``OK`` row, the others are UNKNOWN or a disclosed "short section".
"""

from collections.abc import Collection, Sequence
from datetime import date, datetime

import pandas as pd

from algotrade.data.events import ALL_TIME, acceptance_sessions
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import KNOWN_FROM

TABLE = "events/filing_text"
OK = "OK"
KEY_COLUMNS = (
    "instrument_id",
    "ts",
    "known_from",
    "accession",
    "item",
    "parser_version",
    "quality",
)
COLUMNS = (
    "instrument_id",
    "ts",
    "known_from",
    "cik",
    "form",
    "accession",
    "filing_date",
    "report_date",
    "item",
    "parser_version",
    "text",
    "char_count",
    "quality",
    "reason",
)
_NO_ITEM = "\x00"  # a null item in a group key (null == null for the version rule)


def effective_known_from(frame: pd.DataFrame) -> pd.Series:
    """Each row's ``known_from`` as a midnight datetime: the stored one, never earlier than the
    acceptance session of its ``ts`` (module doc)."""
    stored = pd.to_datetime(frame[KNOWN_FROM])
    floor = pd.to_datetime(acceptance_sessions(frame["ts"]))
    return pd.concat([stored, floor], axis=1).max(axis=1)


def latest_filing_versions(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per (instrument, accession, item): the one with the latest effective
    ``known_from``, then ``parser_version``, then ``knowledge_ts``; ``known_from`` is replaced by
    the effective date. Null items group together."""
    if frame.empty:
        return frame.reset_index(drop=True)
    out = frame.assign(known_from=effective_known_from(frame), _item=frame["item"].fillna(_NO_ITEM))
    out = out.sort_values(["known_from", "parser_version", "knowledge_ts"], kind="stable")
    out = out.drop_duplicates(["instrument_id", "accession", "_item"], keep="last")
    return out.drop(columns="_item").assign(known_from=lambda f: f["known_from"].dt.date)


def _without_empty_filing_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Drop the null-item row of a filing that has an item row (module doc)."""
    has_items = frame.loc[frame["item"].notna(), ["instrument_id", "accession"]].drop_duplicates()
    keyed = frame.merge(
        has_items.assign(_items=True), how="left", on=["instrument_id", "accession"]
    )
    return frame[~(frame["item"].isna().to_numpy() & keyed["_items"].eq(True).to_numpy())]


def stored_filing_text(
    reader: StoreReader,
    instrument_ids: Sequence[str],
    columns: Sequence[str] = KEY_COLUMNS,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """Every stored row of ``instrument_ids`` as stored (every version, any ``known_from``),
    with ``columns`` (default ``KEY_COLUMNS``; add ``text`` for a comparison) plus the stamps;
    the producer's read of what it already holds. Empty when nothing is stored."""
    frame = reader.table_range(TABLE, *ALL_TIME, as_of, list(instrument_ids), list(columns))
    if frame is None or frame.empty:
        return pd.DataFrame({c: [] for c in (*columns, "knowledge_ts", "session_date")})
    return frame.reset_index(drop=True)


def filing_text(
    reader: StoreReader,
    instrument_ids: Sequence[str],
    on: date,
    items: Collection[str] | None = None,
    forms: Collection[str] | None = None,
    since: date | None = None,
    as_of: datetime | None = None,
    with_text: bool = True,
) -> pd.DataFrame:
    """The item rows (``COLUMNS``) of ``instrument_ids`` known on or before session ``on`` (module
    doc), the latest version of each, for filings accepted on or after ``since`` and the
    ``items`` / ``forms`` asked (``None``: all); sorted by instrument, acceptance, accession and
    item. ``with_text=False`` leaves ``text`` out of the read (a scan of what is there). Empty
    (with the columns) when nothing is known."""
    wanted = [c for c in COLUMNS if with_text or c != "text"]
    frame = reader.table_range(
        TABLE, since or ALL_TIME[0], on, as_of, list(instrument_ids), list(wanted)
    )
    if frame is None or frame.empty:
        return pd.DataFrame({c: [] for c in wanted})
    frame = frame[effective_known_from(frame) <= pd.Timestamp(on)]  # known first, then the latest
    frame = latest_filing_versions(frame)
    frame = _without_empty_filing_rows(frame)
    if items is not None:
        frame = frame[frame["item"].isin(list(items))]
    if forms is not None:
        frame = frame[frame["form"].isin(list(forms))]
    order = ["instrument_id", "ts", "accession", "item"]
    return (
        frame[wanted].sort_values(order, kind="stable", na_position="first").reset_index(drop=True)
    )
