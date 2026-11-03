"""``listing-history-merge``: Tiingo's file rows and Massive's inactive records as one frame of
``instruments/listing_history`` rows, before ids (ADR 0087, decision 2). Pure: no store, no
network (the one vendor question, Tiingo's meta for a Massive-only record, comes in as
``ask_meta``). Ids are ``tasks/reference/instrument_ids.assign_listing_ids``'s, never decided here.

Nothing a free source sent is discarded (owner tenet 2026-11-01): every Tiingo row and every
Massive record is a row; what cannot be placed carries a null and a reason in ``no_id_reason``.

**Compare key**: the ticker upper-cased, ``.`` read as ``-`` (``BRK.B`` is ``BRK-B``). A ``$``
(preferred) never pairs.

**Pairing.** An ended in-scope Tiingo row pairs with a Massive record of the same key whose
last trading day is within ``PAIR_DAYS`` calendar days of its own end, when each is the other's
only such neighbour; several neighbours either way is ``pair_ambiguous`` and none of them pairs
(a reused ticker). An open Tiingo row, or a Massive record with no end date, never pairs. A
paired row (source ``tiingo``) takes every Massive attribute; ``vendor_end_date`` is Massive's end.

**A Massive-only record** (no Tiingo row paired) is always written, as a ``source = massive`` row:
its ``exchange`` from the MIC (``EXCHANGE_BY_MIC``; an unmapped MIC is ``other_exchange``, out of
scope), ``asset_type`` ETF when ``security_type`` is ETF, else Stock, ``end_date`` its last
trading day. Its start date is never guessed; it comes from a Tiingo row of the same company
and is otherwise null, with the reason in ``no_id_reason`` (a null start is never in the
universe: ``data.listings`` counts them as undated). In this order:

1. ``pair_ambiguous``: it had several candidates to pair with.
2. ``no_start``: it has no end date to look a successor up by.
3. ``overlaps_listing``: an in-scope Tiingo row of its own ticker covers its last day (the
   ticker was reused: that row's life is not this record's); checked again once a start is
   found: no in-scope Tiingo row of the ticker may overlap the whole life ``start..end``, or the
   one name would be listed twice (a Tiingo row that ended days before the record's end).
4. ``no_start``: no candidate. Candidates are the out-of-scope ``other_exchange`` Tiingo rows
   (the OTC successor a bankrupt name moves to: ``BBBY`` -> ``BBBYQ``) whose ticker starts with
   the record's and is at most ``SUFFIX`` characters longer, that started on or before the
   record's last day and have no end or ended no more than ``PAIR_DAYS`` days before it.
5. One Tiingo meta request, for the record's ticker and its candidates' (one request per record
   that has candidates). The record takes the permaTicker ``P`` only when exactly one
   permaTicker sits on both a meta row of the record's own ticker, inactive there, and the meta
   rows of exactly one candidate; then its start is that candidate's. Otherwise
   ``perma_ambiguous``, or ``no_meta`` when the record's own ticker has no meta row (an unrelated
   OTC name proves nothing). Recorded 2026-11-01: ``bbby`` answers a reused ticker's permaTicker
   (active) and ``bbbyq`` Bed Bath & Beyond's: no common permaTicker, BBBY stays undated, the
   safe outcome.

6. Details (PR3b, optional ``details`` frame, ``data.listings.delisted.read_delisted_details``):
   a record the steps above leave as ``no_start``, ``perma_ambiguous`` or ``no_meta`` (never
   ``pair_ambiguous`` or ``overlaps_listing``) takes the ``list_date`` of Massive's ticker details
   asked at its last day (``delisted-details``: the company as it was then) as its start when a
   details row of the same (ticker, end date) is found, ``list_date <= end``, the identity agrees
   (CIK equal when both are present, composite FIGI equal when both are present, and the details'
   ``delisted_date``, when present, within ``PAIR_DAYS`` of the record's end) and no in-scope
   Tiingo row of the ticker overlaps ``list_date..end`` (else ``overlaps_listing``). A refused
   detail leaves the old reason; the refusals are counted (``details_mismatch``,
   ``details_after_end``, ``details_overlaps``, with ``details_dated`` the accepted).

``start_source`` says where a start came from: ``tiingo`` (a Tiingo row's own), ``perma_successor``
(step 5) or ``massive_details`` (step 6); null where there is no start.

The end date is read here (identity: pairing and the id), never as a feature or label.
"""

from collections import Counter
from collections.abc import Callable, Hashable, Mapping, Sequence
from datetime import date, timedelta
from typing import Any

import pandas as pd

from algotrade.data.listings.delisted import EXCHANGE_BY_MIC

TIINGO = "tiingo"
MASSIVE = "massive"
OTHER_EXCHANGE = "other_exchange"
PAIR_DAYS = 7  # calendar days between the two vendors' last trading days of one listing
SUFFIX = 2  # characters an OTC successor's ticker may add (BBBY -> BBBYQ)
PAIR_AMBIGUOUS = "pair_ambiguous"
NO_START = "no_start"
OVERLAPS = "overlaps_listing"
PERMA_AMBIGUOUS = "perma_ambiguous"
NO_META = "no_meta"
TIINGO_START = "tiingo"  # ``start_source`` values
PERMA_SUCCESSOR = "perma_successor"
MASSIVE_DETAILS = "massive_details"
LIFTABLE = (NO_START, PERMA_AMBIGUOUS, NO_META)  # reasons a details ``list_date`` can lift
MASSIVE_ATTRIBUTES = ("name", "vendor_type", "security_type", "cik", "figi", "share_class_figi")
COLUMNS = [
    "source", "ticker", "exchange", "asset_type", "price_currency", "start_date", "end_date",
    "perma_ticker", "scope_reason", "name", "vendor_type", "security_type", "cik", "figi",
    "share_class_figi", "vendor_exchange", "vendor_end_date", "is_adr",
    "data_provider_perma_ticker", "no_id_reason", "start_source",
]  # fmt: skip
AskMeta = Callable[[Sequence[str]], pd.DataFrame | None]  # tickers -> meta rows, None: no answer
Row = dict[str, Any]
Details = dict[tuple[str, date], Row]  # (ticker, last day) -> a found details row


def _none(value: Any) -> Any:
    """``value``, or ``None`` for a missing one (NaN, NaT)."""
    return (
        None if value is None or (not isinstance(value, list | dict) and pd.isna(value)) else value
    )


def _cells(record: Mapping[Hashable, Any], **extra: Any) -> Row:
    """A frame record as a ``COLUMNS`` row: missing cells ``None``, ``extra`` set."""
    return {**dict.fromkeys(COLUMNS), **{str(k): _none(v) for k, v in record.items()}, **extra}


def _label(value: Any) -> str | None:
    value = _none(value)
    return None if value is None or not str(value).strip() else str(value).strip()


def _day(value: Any) -> date | None:
    value = _none(value)
    return None if value is None else pd.Timestamp(str(value)).date()


def compare_key(ticker: Any) -> str | None:
    """The key two vendors' tickers are compared by; ``None`` for a preferred (``$``) or none."""
    text = _label(ticker)
    if text is None or "$" in text:
        return None
    return text.upper().replace(".", "-")


def _near(a: date, b: date) -> bool:
    return abs((a - b).days) <= PAIR_DAYS


def _keyed(rows: list[Row], wanted: Callable[[Row], bool]) -> dict[str, list[int]]:
    """Row indexes by compare key, for the rows ``wanted`` that have a key."""
    out: dict[str, list[int]] = {}
    for i, row in enumerate(rows):
        key = compare_key(row["ticker"])
        if key is not None and wanted(row):
            out.setdefault(key, []).append(i)
    return out


def _pairs(tiingo: list[Row], massive: list[Row]) -> tuple[dict[int, int], set[int]]:
    """-> (Tiingo row index -> Massive record index, the Massive records left ambiguous)."""
    ended = _keyed(tiingo, lambda r: r["scope_reason"] is None and r["end_date"] is not None)
    dated = _keyed(massive, lambda r: r["end_date"] is not None)
    paired: dict[int, int] = {}
    ambiguous: set[int] = set()
    for key, rows in ended.items():
        records = dated.get(key, [])
        mine = {
            i: [j for j in records if _near(tiingo[i]["end_date"], massive[j]["end_date"])]
            for i in rows
        }
        theirs = {
            j: [i for i in rows if _near(tiingo[i]["end_date"], massive[j]["end_date"])]
            for j in records
        }
        for i, near in mine.items():
            if len(near) == 1 and len(theirs[near[0]]) == 1:
                paired[i] = near[0]
            else:
                ambiguous.update(near)
    return paired, ambiguous


def _massive_row(rec: Row) -> Row:
    """The ``source = massive`` row of a record no Tiingo row paired with (start still null)."""
    mic = _label(rec.get("exchange"))
    exchange = EXCHANGE_BY_MIC.get(mic) if mic else None
    currency = _label(rec.get("currency_name"))
    row: Row = dict.fromkeys(COLUMNS)
    row.update(
        source=MASSIVE, ticker=rec["ticker"], exchange=exchange or mic,
        asset_type="ETF" if _label(rec.get("security_type")) == "ETF" else "Stock",
        price_currency=currency.upper() if currency else None,
        end_date=rec["end_date"], perma_ticker="", vendor_exchange=mic,
        vendor_end_date=rec["end_date"],
        scope_reason=None if exchange else OTHER_EXCHANGE,
        **{c: _label(rec.get(c)) for c in MASSIVE_ATTRIBUTES},
    )  # fmt: skip
    return row


class _Successors:
    """The out-of-scope Tiingo rows on another exchange, found by the ticker they extend."""

    def __init__(self, tiingo: list[Row]) -> None:
        self.rows: dict[str, list[Row]] = {}
        for row in tiingo:
            key = compare_key(row["ticker"])
            if key is None or row["scope_reason"] != OTHER_EXCHANGE or row["start_date"] is None:
                continue
            for length in range(max(1, len(key) - SUFFIX), len(key) + 1):
                self.rows.setdefault(key[:length], []).append(row)

    def of(self, key: str, last: date) -> list[Row]:
        """The candidates for a record with ``key`` and last trading day ``last``."""
        floor = last - timedelta(days=PAIR_DAYS)
        return [
            r for r in self.rows.get(key, [])
            if r["start_date"] <= last and (r["end_date"] is None or r["end_date"] >= floor)
        ]  # fmt: skip


def _covers(rows: list[Row], first: date | None, last: date) -> bool:
    """Whether one of the Tiingo rows was listed on a day of ``first..last`` (``first`` None:
    on ``last``)."""
    return any(
        r["start_date"] <= last and (r["end_date"] is None or r["end_date"] >= (first or last))
        for r in rows
    )


def _by_perma(
    key: str, candidates: list[Row], meta: pd.DataFrame | None
) -> tuple[Row | None, pd.Series | None, str]:
    """-> (the candidate whose start the record takes, the meta row naming the permaTicker, the
    reason when there is none): the module docstring's step 5. One permaTicker must sit on the
    meta rows of both the record's own ticker (inactive there: the old company no longer trades
    under it) and of exactly one candidate."""
    if meta is None or meta.empty:
        return None, None, NO_META
    tickers = meta["ticker"].map(compare_key)
    own = meta[tickers == key]
    if own.empty:  # nothing says what the record's ticker was: an OTC name nearby proves nothing
        return None, None, NO_META
    theirs = meta[tickers.isin({compare_key(c["ticker"]) for c in candidates})]
    common = set(own["perma_ticker"]) & set(theirs["perma_ticker"])
    if len(common) != 1:
        return None, None, PERMA_AMBIGUOUS
    (perma,) = common
    if own.loc[own["perma_ticker"] == perma, "is_active"].any():  # a reused ticker's new company
        return None, None, PERMA_AMBIGUOUS
    named = theirs[theirs["perma_ticker"] == perma]
    keys = {compare_key(t) for t in named["ticker"]}
    starts = [c for c in candidates if compare_key(c["ticker"]) in keys]
    if len(starts) != 1:
        return None, None, PERMA_AMBIGUOUS
    return starts[0], named.iloc[0], ""


def _details_by_record(details: pd.DataFrame | None) -> Details:
    """The found rows of the details frame by (ticker, last day); none for a missing frame."""
    if details is None or details.empty:
        return {}
    out: Details = {}
    for rec in details.to_dict("records"):
        row = _cells(rec)
        last = _day(row.get("end_date"))
        if row.get("found") is True and last is not None and row.get("ticker") is not None:
            out[(str(row["ticker"]), last)] = {
                **row, "list_date": _day(row.get("list_date")),
                "delisted_date": _day(row.get("delisted_date")),
            }  # fmt: skip
    return out


def _disagrees(ours: Any, theirs: Any) -> bool:
    """Two identifiers that are both present and differ."""
    a, b = _label(ours), _label(theirs)
    return a is not None and b is not None and a.upper() != b.upper()


def _from_details(
    row: Row, key: str, details: Details, covering: dict[str, list[Row]], stats: Counter[str]
) -> None:  # fmt: skip
    """Step 6 of the module docstring: take the details' ``list_date`` as ``row``'s start, or
    leave it as it is (counting why not)."""
    if row["no_id_reason"] not in LIFTABLE:
        return
    last = row["end_date"]
    found = details.get((str(row["ticker"]), last))
    if found is None or found["list_date"] is None:
        return
    started, delisted = found["list_date"], found["delisted_date"]
    if started > last:
        stats["details_after_end"] += 1
    elif (
        _disagrees(row["cik"], found.get("cik"))
        or _disagrees(row["figi"], found.get("figi"))
        or (delisted is not None and not _near(delisted, last))
    ):
        stats["details_mismatch"] += 1
    elif _covers(covering.get(key, []), started, last):
        stats["details_overlaps"] += 1
    else:
        row.update(start_date=started, start_source=MASSIVE_DETAILS, no_id_reason=None)
        stats["details_dated"] += 1


def _date_record(
    row: Row, successors: _Successors, covering: dict[str, list[Row]], ask_meta: AskMeta,
    details: Details, stats: Counter[str],
) -> None:  # fmt: skip
    """Give ``row`` (a Massive-only record) a start and a permaTicker, or the reason it has none."""
    _by_successor(row, successors, covering, ask_meta, stats)
    key = compare_key(row["ticker"])
    if key is not None and row["end_date"] is not None:
        _from_details(row, key, details, covering, stats)


def _by_successor(
    row: Row, successors: _Successors, covering: dict[str, list[Row]], ask_meta: AskMeta,
    stats: Counter[str],
) -> None:  # fmt: skip
    """Steps 2 to 5 of the module docstring."""
    key, last = compare_key(row["ticker"]), row["end_date"]
    if key is None or last is None:
        row["no_id_reason"] = NO_START
        return
    if _covers(covering.get(key, []), None, last):
        row["no_id_reason"] = OVERLAPS
        return
    candidates = successors.of(key, last)
    if not candidates:
        row["no_id_reason"] = NO_START
        return
    asked = list(dict.fromkeys([key, *(str(compare_key(c["ticker"])) for c in candidates)]))
    stats["meta_record_requests"] += 1
    start, meta_row, reason = _by_perma(key, candidates, ask_meta(asked))
    if start is None or meta_row is None:
        row["no_id_reason"] = reason
        return
    if _covers(covering.get(key, []), start["start_date"], last):  # the dated life meets another
        row["no_id_reason"] = OVERLAPS
        return
    row.update(
        start_date=start["start_date"], start_source=PERMA_SUCCESSOR,
        perma_ticker=str(meta_row["perma_ticker"]),
        data_provider_perma_ticker=_label(meta_row.get("data_provider_perma_ticker")),
        is_adr=bool(meta_row.get("is_adr", False)),
    )  # fmt: skip


def merge_listings(
    tiingo: pd.DataFrame,
    massive: pd.DataFrame,
    ask_meta: AskMeta,
    details: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """``tiingo`` (every file row, ``tiingo.listings.COLUMNS``) and ``massive`` (the inactive
    snapshot: ``ticker``, ``end_date``, ``exchange`` the MIC, the Massive attributes) -> (the
    rows of ``COLUMNS``, stats). ``ask_meta(tickers)`` answers Tiingo's meta rows of those
    tickers, or ``None``. ``details``: the stored Massive ticker details (step 6), none by
    default."""
    rows: list[Row] = [_cells(r, source=TIINGO) for r in tiingo.to_dict("records")]
    for row in rows:
        row["start_date"], row["end_date"] = _day(row["start_date"]), _day(row["end_date"])
        row["start_source"] = TIINGO_START if row["start_date"] is not None else None
    records: list[Row] = [_cells(r) for r in massive.to_dict("records")]
    for rec in records:
        rec["end_date"] = _day(rec.get("end_date"))
    paired, ambiguous = _pairs(rows, records)
    for i, j in paired.items():
        rows[i].update({c: _label(records[j].get(c)) for c in MASSIVE_ATTRIBUTES})
        rows[i].update(
            vendor_exchange=_label(records[j].get("exchange")),
            vendor_end_date=records[j]["end_date"],
        )
    stats: Counter[str] = Counter(
        paired=len(paired), massive_records=len(records), pair_ambiguous_records=len(ambiguous),
        meta_record_requests=0, details_dated=0, details_mismatch=0, details_after_end=0,
        details_overlaps=0,
    )  # fmt: skip
    only = _massive_only(
        rows, records, set(paired.values()), ambiguous, ask_meta, _details_by_record(details), stats
    )
    stats["massive_only"] = len(only)
    stats["massive_dated"] = sum(1 for r in only if r["start_date"] is not None)
    stats.update(f"massive_{r['no_id_reason']}" for r in only if r["no_id_reason"])
    return pd.DataFrame([*rows, *only], columns=COLUMNS), dict(stats)


def _massive_only(
    rows: list[Row], records: list[Row], paired: set[int], ambiguous: set[int], ask_meta: AskMeta,
    details: Details, stats: Counter[str],
) -> list[Row]:  # fmt: skip
    """The ``source = massive`` rows of the records no Tiingo row paired with, dated where the
    module docstring says they can be."""
    successors = _Successors(rows)
    covering: dict[str, list[Row]] = {}
    for key, indexes in _keyed(rows, lambda r: r["scope_reason"] is None).items():
        covering[key] = [rows[i] for i in indexes]
    only = []
    for j, rec in enumerate(records):
        if j in paired:
            continue
        row = _massive_row(rec)
        if row["scope_reason"] is not None:
            stats["massive_out_of_scope"] += 1
        elif j in ambiguous:
            row["no_id_reason"] = PAIR_AMBIGUOUS
        else:
            _date_record(row, successors, covering, ask_meta, details, stats)
        only.append(row)
    return only
