"""Item sections of 10-K / 10-Q filings (``events/filing_text``) for consumers and the producer.

One row per filer (``cik``), filing (``accession``: a 10-K/A is its own filing), item and
``parser_version``; ``item`` is null on the one row of a filing no header was found in. Every
10-K / 10-Q filer is stored, delisted companies included (edge build D10b), so the table is
keyed by the filer, not by an instrument.

**The read rule** (ADR 0007, ADR 0050 decision 3): as of session S a row is known when its
effective ``known_from`` is on or before S, the stored ``known_from`` floored by the acceptance
session recomputed from ``ts`` (``events.acceptance_sessions``), so a row can never be read before
its filing was public, whatever stamp it carries. Per (cik, accession, item) the version
read is the latest known: highest ``known_from``, then ``parser_version``, then ``knowledge_ts``.
A later parser version that changed a text is known only from the day it ran (the producer
stamps it), so a read before that day sees the older text; one that did not change it carries
the older row's ``known_from``. The null-item row of a filing is dropped when the filing has an
item row (an earlier parser found nothing, a later one did), never the other way round: a later
parser that finds nothing does not erase items an earlier one found.

**Instruments**: ``instrument_id`` is NULL on a filing's first version (the producer's universe is
today's, the row is known from an old session) and is filled by a later version of the same
(cik, accession, item), known from the session the producer filled it. A read at S before that
shows NULL; from it the id. ``filing_text(..., ids)`` instead maps the ids to their CIKs through
``instruments/company`` as of S (plus the ids a known version carries), so a listed name reads its
filings whatever the stored id; ``ids=None`` is the scan of every filer (``ciks`` narrows it), with
the stored id, NULL or not.

Rows carry ``quality`` (``OK``, ``SHORT``, ``TRUNCATED``, ``NOT_FOUND``, ``NO_ITEMS``); a text
read for a signal is an ``OK`` row, the others are UNKNOWN or a disclosed "short section".
"""

from collections.abc import Collection, Sequence
from datetime import date, datetime

import pandas as pd

from algotrade.core.model.instruments import pad_cik
from algotrade.data.events import ALL_TIME, acceptance_sessions
from algotrade.data.reference import companies
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
    "cik",
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
    """One row per (cik, accession, item): the one with the latest effective
    ``known_from``, then ``parser_version``, then ``knowledge_ts``; ``known_from`` is replaced by
    the effective date. Null items group together."""
    if frame.empty:
        return frame.reset_index(drop=True)
    out = frame.assign(known_from=effective_known_from(frame), _item=frame["item"].fillna(_NO_ITEM))
    out = out.sort_values(["known_from", "parser_version", "knowledge_ts"], kind="stable")
    out = out.drop_duplicates(["cik", "accession", "_item"], keep="last")
    return out.drop(columns="_item").assign(known_from=lambda f: f["known_from"].dt.date)


def _without_empty_filing_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Drop the null-item row of a filing that has an item row (module doc)."""
    has_items = frame.loc[frame["item"].notna(), ["cik", "accession"]].drop_duplicates()
    keyed = frame.merge(has_items.assign(_items=True), how="left", on=["cik", "accession"])
    return frame[~(frame["item"].isna().to_numpy() & keyed["_items"].eq(True).to_numpy())]


def stored_filing_text(
    reader: StoreReader,
    instrument_ids: Sequence[str] | None,
    columns: Sequence[str] = KEY_COLUMNS,
    as_of: datetime | None = None,
    start: date | None = None,
    end: date | None = None,
    ciks: Collection[str] | None = None,
) -> pd.DataFrame:
    """Every stored row of ``instrument_ids`` (``None``: every filer) as stored (every version,
    any ``known_from``), with ``columns`` (default ``KEY_COLUMNS``; add ``text`` for a comparison)
    plus the stamps; ``ciks`` keeps only those filers' rows (a filter after the read: the store
    indexes no cik). The producer's read of what it already holds, from the acceptance-session
    partitions of ``start..end`` (default: all). Empty when nothing is stored."""
    wanted = list(columns) if ciks is None or "cik" in columns else [*columns, "cik"]
    ids = None if instrument_ids is None else list(instrument_ids)
    frame = reader.table_range(TABLE, start or ALL_TIME[0], end or ALL_TIME[1], as_of, ids, wanted)
    if frame is None or frame.empty:
        return pd.DataFrame({c: [] for c in (*wanted, "knowledge_ts", "session_date")})
    if ciks is not None:
        frame = frame[frame["cik"].isin(list(ciks))]
    return frame.reset_index(drop=True)


def _instruments_of(
    reader: StoreReader, ids: Sequence[str], on: date, as_of: datetime | None
) -> dict[str, list[str]]:
    """CIK -> the requested ids that have it in the ``instruments/company`` snapshot on or before
    ``on`` (a later snapshot never stands in); empty before the first snapshot."""
    found = companies(reader, on, list(ids), as_of)
    if found is None or found.empty or "cik" not in found.columns:
        return {}
    out: dict[str, list[str]] = {}
    for iid, cik in zip(found["instrument_id"], found["cik"], strict=True):
        if (padded := pad_cik(cik)) is not None:
            out.setdefault(padded, []).append(str(iid))
    return out


def _with_text(reader: StoreReader, frame: pd.DataFrame, as_of: datetime | None) -> pd.DataFrame:
    """``frame`` (the chosen versions, ``_kf`` the stored ``known_from``) with ``text``, read one
    acceptance-session partition at a time, only the days the rows are in."""
    key = ["cik", "accession", "_item", "parser_version", "_kf"]
    days = sorted(set(pd.to_datetime(frame["session_date"]).dt.date))
    parts = []
    for day in days:
        part = reader.table_range(
            TABLE,
            day,
            day,
            as_of,
            None,
            ["cik", "accession", "item", "parser_version", "known_from", "text"],
        )
        if part is not None and not part.empty:
            parts.append(
                part.assign(_item=part["item"].fillna(_NO_ITEM), _kf=part["known_from"])[
                    [*key, "text"]
                ]
            )
    if not parts:
        return frame.assign(text=None)
    texts = pd.concat(parts, ignore_index=True).drop_duplicates(key, keep="last")
    return frame.merge(texts, how="left", on=key)


def filing_text(
    reader: StoreReader,
    instrument_ids: Sequence[str] | None,
    on: date,
    items: Collection[str] | None = None,
    forms: Collection[str] | None = None,
    since: date | None = None,
    as_of: datetime | None = None,
    with_text: bool = True,
    ciks: Collection[str] | None = None,
) -> pd.DataFrame:
    """The item rows (``COLUMNS``) known on or before session ``on`` (module doc), the latest
    version of each (cik, accession, item), for filings accepted on or after ``since`` and the
    ``items`` / ``forms`` asked (``None``: all); sorted by instrument, acceptance, cik, accession
    and item. ``instrument_ids``: those instruments' filings, mapped through the company snapshot
    as of ``on`` (a CIK of two share classes gives a row set each), ``instrument_id`` the
    requested one; ``None``: every filer, ``instrument_id`` as stored (NULL before the producer's
    id version is known), ``ciks`` narrowing the scan. ``with_text=False`` leaves ``text`` out of
    the read (a scan of what is there). Empty (with the columns) when nothing is known."""
    wanted = [c for c in COLUMNS if with_text or c != "text"]
    light = [c for c in COLUMNS if c != "text"]
    frame = reader.table_range(TABLE, since or ALL_TIME[0], on, as_of, None, light)
    if frame is None or frame.empty:
        return pd.DataFrame({c: [] for c in wanted})
    frame = frame[effective_known_from(frame) <= pd.Timestamp(on)]  # known first, then the latest
    mapping: dict[str, list[str]] = {}
    if instrument_ids is not None:
        mapping = _instruments_of(reader, instrument_ids, on, as_of)
        carried = frame[frame["instrument_id"].isin(list(instrument_ids))]
        for cik, iid in zip(carried["cik"], carried["instrument_id"], strict=True):
            mapping.setdefault(str(cik), [])
            if iid not in mapping[str(cik)]:
                mapping[str(cik)].append(str(iid))
        frame = frame[frame["cik"].isin(list(mapping))]
    if ciks is not None:
        frame = frame[frame["cik"].isin([pad_cik(c) for c in ciks])]
    if frame.empty:
        return pd.DataFrame({c: [] for c in wanted})
    frame = latest_filing_versions(frame.assign(_kf=frame["known_from"]))
    frame = _without_empty_filing_rows(frame)
    if items is not None:
        frame = frame[frame["item"].isin(list(items))]
    if forms is not None:
        frame = frame[frame["form"].isin(list(forms))]
    if frame.empty:
        return pd.DataFrame({c: [] for c in wanted})
    if with_text:
        frame = _with_text(reader, frame.assign(_item=frame["item"].fillna(_NO_ITEM)), as_of)
    if instrument_ids is not None:
        frame = pd.concat(
            [
                frame[frame["cik"] == c].assign(instrument_id=i)
                for c, ids in mapping.items()
                for i in ids
            ],
            ignore_index=True,
        )
    order = ["instrument_id", "ts", "cik", "accession", "item"]
    return (
        frame[wanted].sort_values(order, kind="stable", na_position="first").reset_index(drop=True)
    )
