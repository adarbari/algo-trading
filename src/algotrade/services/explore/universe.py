"""The universe as a filterable, paged table (fixed columns, or tickers x any catalogue
columns for Explore), and the owner's review lists (FIGI, leverage).

A universe row is the coverage snapshot (``universe``) joined with reference facts, company
sector / industry and the liquidity class (an expression feature) for the same session
(``services.features.field_view``).
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from algotrade.core.model.errors import ConfigurationError
from algotrade.data.reference import (
    UNIVERSE_TABLE,
    Universe,
    instruments,
    load_universe,
)
from algotrade.services.configs import catalog_of
from algotrade.services.explore.store import (
    NotFoundError,
    Page,
    ReadStore,
    paginate,
    partition_for,
    records,
    store_features,
)
from algotrade.services.features import field_view

REFERENCE = "instruments/reference"
UNIVERSE_BUILD = "universe_build"  # the job that records the FIGI review list in its stats
LIQUIDITY = "feature.liquidity_class"
VIEW_FIELDS = {
    "instrument.is_leveraged": "is_leveraged",
    "instrument.is_inverse": "is_inverse",
    "instrument.leverage": "leverage",
    "instrument.in_sp500": "in_sp500",
    "instrument.sector": "sector",
    "instrument.industry": "industry",
    LIQUIDITY: "liquidity_class",
}
BASE = ("instrument_id", "symbol", "company_name", "security_type", "asset_class", "exchange")
COLUMNS = (*BASE, "optionable", *VIEW_FIELDS.values())
TICKER_BASE = ("instrument_id", "symbol", "company_name", "security_type")


@dataclass(frozen=True)
class UniverseFilter:
    security_type: str | None = None
    leveraged: bool | None = None
    sector: str | None = None
    liquidity_class: str | None = None
    q: str | None = None  # symbol or company name contains (case-insensitive)


@dataclass(frozen=True)
class UniversePage:
    session: date
    snapshot_date: date
    pre_snapshot: bool
    version: str
    missing: list[str]  # tables with no partition for the session (their columns are null)
    page: Page[dict[str, Any]]


def _same(values: pd.Series, wanted: str) -> pd.Series:
    return values.astype("string").str.casefold().eq(wanted.casefold()).fillna(False)


def _filtered(frame: pd.DataFrame, f: UniverseFilter) -> pd.DataFrame:
    keep = pd.Series(True, index=frame.index)
    if f.security_type:
        keep &= _same(frame["security_type"], f.security_type)
    if f.sector:
        keep &= _same(frame["sector"], f.sector)
    if f.liquidity_class:
        keep &= _same(frame["liquidity_class"], f.liquidity_class)
    if f.leveraged is not None:
        keep &= frame["is_leveraged"].astype("boolean").eq(f.leveraged).fillna(False)
    if f.q:
        text = frame["symbol"].astype("string") + " " + frame["company_name"].astype("string")
        keep &= text.str.contains(f.q, case=False, regex=False).fillna(False)
    return frame[keep]


def _universe(
    store: ReadStore, on: date | None, columns: list[str]
) -> tuple[pd.DataFrame, Universe, list[str]]:
    """The universe for ``on`` (the latest snapshot when None) joined with ``VIEW_FIELDS``
    (short names) and ``columns`` (by field name) -> (frame, universe, missing tables)."""
    session = on or partition_for(store.reader, UNIVERSE_TABLE, None)
    universe = load_universe(store.reader, session)
    fields = list(dict.fromkeys([*VIEW_FIELDS, *columns]))
    view = field_view(store.reader, session, fields, features=store_features(store))
    frame = universe.frame.reindex(columns=[*BASE, "optionable"])
    frame["instrument_id"] = frame["instrument_id"].astype(str)
    extra = view.frame.reindex(columns=["instrument_id", *fields])
    for name, short in VIEW_FIELDS.items():
        extra[short] = extra[name]
    frame = frame.merge(extra, on="instrument_id", how="left")
    return frame, universe, list(view.missing)


def universe_page(
    store: ReadStore, on: date | None, filters: UniverseFilter, page: int, size: int
) -> UniversePage:
    """The universe for ``on`` (the latest snapshot when None), filtered, sorted by symbol."""
    frame, universe, missing = _universe(store, on, [])
    frame = _filtered(frame, filters).sort_values("symbol", kind="stable")
    return UniversePage(
        session=on or universe.snapshot_date,
        snapshot_date=universe.snapshot_date,
        pre_snapshot=universe.pre_snapshot,
        version=universe.version,
        missing=missing,
        page=paginate(records(frame[list(COLUMNS)]), page, size),
    )


@dataclass(frozen=True)
class TickerTable:
    session: date
    snapshot_date: date
    pre_snapshot: bool
    columns: list[str]  # the requested feature columns, in order
    sort: str  # the column sorted by ("-" prefix: descending; nulls always last)
    missing: list[str]  # tables with no partition for the session (their columns are null)
    page: Page[dict[str, Any]]  # TICKER_BASE + one key per requested column


def checked_columns(store: ReadStore, columns: list[str]) -> list[str]:
    """``columns`` without duplicates; ``ConfigurationError`` for a name not in the user's
    catalogue (site + their own features)."""
    catalogue = catalog_of(store_features(store))
    for name in columns:
        catalogue.check_field(name, "columns")
    return list(dict.fromkeys(columns))


def _sorted(frame: pd.DataFrame, sort: str) -> pd.DataFrame:
    column = sort.removeprefix("-")
    if column not in frame.columns:
        raise ConfigurationError(f"sort: {column!r} is not a returned column")
    keys = list(dict.fromkeys([column, "symbol"]))
    ascending = [not sort.startswith("-"), True][: len(keys)]
    return frame.sort_values(keys, ascending=ascending, na_position="last", kind="stable")


def ticker_table(
    store: ReadStore,
    on: date | None,
    filters: UniverseFilter,
    columns: list[str],
    sort: str | None,
    page: int,
    size: int,
) -> TickerTable:
    """The universe for ``on`` as tickers x ``columns`` (catalogue field names: reference,
    company, rollup and expression-feature values for the session), filtered, sorted."""
    wanted = checked_columns(store, columns)
    frame, universe, missing = _universe(store, on, wanted)
    order = sort or "symbol"
    frame = _sorted(_filtered(frame, filters)[[*TICKER_BASE, *wanted]], order)
    return TickerTable(
        session=on or universe.snapshot_date,
        snapshot_date=universe.snapshot_date,
        pre_snapshot=universe.pre_snapshot,
        columns=wanted,
        sort=order,
        missing=missing,
        page=paginate(records(frame), page, size),
    )


@dataclass(frozen=True)
class ReviewList:
    session: date | None
    source: str  # where the rows come from: a run id, or the reference snapshot
    items: list[dict[str, Any]]


def figi_review(store: ReadStore) -> ReviewList:
    """Listings marked for FIGI review, as the latest universe build recorded them; without
    such a record, the marked rows of the latest reference snapshot."""
    for run in reversed(store.reader.runs(UNIVERSE_BUILD)):
        if "figi_review" in run.stats:
            return ReviewList(run.session_date, run.run_id, list(run.stats["figi_review"]))
    session = partition_for(store.reader, REFERENCE, None)
    ref = instruments(store.reader, session)
    if "vendor_figi" not in ref.columns:
        return ReviewList(session, REFERENCE, [])
    marked = ref[ref["status"].eq("ACTIVE") & ref["vendor_figi"].notna()].sort_values("symbol")
    columns = ["symbol", "instrument_id", "figi", "vendor_figi", "figi_review_since"]
    return ReviewList(session, REFERENCE, records(marked.reindex(columns=columns)))


def leverage_review(store: ReadStore, on: date | None = None) -> ReviewList:
    """Active ETFs whose leverage the rules could not classify (``leverage_source`` =
    ``needs_review``: UNKNOWN until curated in ``config/site/overrides``)."""
    session = partition_for(store.reader, REFERENCE, on)
    ref = instruments(store.reader, session)
    if "leverage_source" not in ref.columns:
        raise NotFoundError(f"{REFERENCE} {session}: no leverage classification stored")
    pending = ref[ref["leverage_source"].eq("needs_review") & ref["status"].eq("ACTIVE")]
    columns = ["symbol", "instrument_id", "name", "security_type", "exchange"]
    return ReviewList(session, REFERENCE, records(pending.sort_values("symbol")[columns]))
