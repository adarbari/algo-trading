"""Canonical table schemas: the data contract every writer must satisfy.

Every row carries the point-in-time columns (ADR 0007). Market tables also carry ``ts``.
Fixed tables declare every column with an abstract type (``COLUMN_TYPES``) and nullability;
storage backends cast writes to those types (and fail on uncastable data), stamp
``SCHEMA_VERSION`` and the table name into each file, and cast older files on read.
Feature, event, catalogue and result tables are open-ended: they need the common columns
plus ``instrument_id`` (+ ``ts`` for events), which are typed; the rest is defined by the
feature, event source or screener that produces them.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from algotrade.core.model.errors import DataValidationError
from algotrade.core.validation.bars import ohlcv_problems
from algotrade.core.views.series import FIELDS

# Stamped into every Parquet file's metadata with the table name (storage backends). Bump it
# when a declared type changes; readers cast older files to today's declared types.
SCHEMA_VERSION = 1
COMMON = ("session_date", "knowledge_ts", "source", "run_id")
# Abstract column types; storage backends map them to physical types (Arrow, DuckDB later).
COLUMN_TYPES = frozenset({"string", "float64", "int64", "bool", "date", "timestamp_utc"})


@dataclass(frozen=True)
class Column:
    name: str
    type: str  # one of COLUMN_TYPES
    nullable: bool = True

    def __post_init__(self) -> None:
        if self.type not in COLUMN_TYPES:
            raise ValueError(f"{self.name}: unknown column type {self.type!r}")


@dataclass(frozen=True)
class TableSpec:
    """A table's contract. ``columns`` declares types: every column of a fixed table (others
    are rejected on write); the common and key columns of an open-ended one (the producer
    defines the rest). Writes cast to the declared types and fail on uncastable data."""

    name: str
    grain: str
    required: tuple[str, ...]
    open_ended: bool = False
    columns: tuple[Column, ...] = ()

    def column(self, name: str) -> Column | None:
        return next((c for c in self.columns if c.name == name), None)


def _columns(*specs: str) -> tuple[Column, ...]:
    """``"name type"`` (``type!``: not nullable) + the point-in-time columns."""
    out = []
    for spec in (*specs, "session_date date!", "knowledge_ts timestamp_utc!", "source string!",
                 "run_id string!"):  # fmt: skip
        name, kind = spec.split()
        out.append(Column(name, kind.rstrip("!"), not kind.endswith("!")))
    return tuple(out)


def _fixed(name: str, grain: str, required: tuple[str, ...], *columns: str) -> TableSpec:
    spec = TableSpec(name, grain, required, columns=_columns(*columns))
    undeclared = [c for c in (*COMMON, *required) if spec.column(c) is None]
    if undeclared:
        raise ValueError(f"{name}: required columns without a type: {undeclared}")
    return spec


def _strings(*names: str) -> tuple[str, ...]:
    return tuple(f"{n} string" for n in names)


def _floats(*names: str) -> tuple[str, ...]:
    return tuple(f"{n} float64" for n in names)


UNIVERSE = _fixed(
    "universe",
    "universe",
    ("instrument_id", "symbol", "security_type", "optionable", "status", "universe_version"),
    "instrument_id string!",
    "optionable bool",
    *_strings("symbol", "company_name", "security_type", "asset_class", "exchange", "status"),
    *_strings("universe_version", "last_verified", "source_crosscheck", "notes"),
    # CSV import mode keeps the master file's leverage columns as written (typed in L1).
    *_strings("is_leveraged", "is_inverse", "leverage", "tracks"),
)
UNDERLYING_QUOTES = _fixed(
    "chains/underlying_quotes",
    "chain_snapshot",
    ("instrument_id", "symbol", "ts", "price", "close", "volume", "iv30"),
    "instrument_id string!",
    "ts timestamp_utc!",
    *_strings("symbol", "security_type"),
    *_floats("price", "open", "high", "low", "close", "prev_close", "volume", "iv30"),
)
OPTION_QUOTES = _fixed(
    "chains/option_quotes",
    "chain_snapshot",
    (
        "instrument_id",
        "underlying_id",
        "ts",
        "expiry",
        "right",
        "strike",
        "bid",
        "ask",
        "volume",
        "open_interest",
        "iv",
        "delta",
    ),
    "instrument_id string!",
    "ts timestamp_utc!",
    "expiry date",
    *_strings("underlying_id", "root", "right"),
    *_floats("strike", "bid", "ask", "bid_size", "ask_size", "last", "volume", "open_interest"),
    *_floats("iv", "delta", "gamma", "theta", "vega", "rho", "theo"),
)
CHAIN_STATUS = _fixed(
    "chains/status",
    "chain_snapshot",
    ("instrument_id", "status"),
    "instrument_id string!",
    *_strings("symbol", "status"),
)

# L1: what each instrument is (one full snapshot per date). See docs/design/phase-0.md.
INSTRUMENT_REFERENCE = _fixed(
    "instruments/reference",
    "reference",
    ("instrument_id", "symbol", "asset_class", "security_type", "multiplier", "status"),
    "instrument_id string!",
    *_strings("symbol", "name", "asset_class", "security_type", "security_type_source"),
    *_strings("exchange", "currency", "financial_status", "status", "vendor_type"),
    *_strings("figi", "share_class_figi", "cik", "tracks", "leverage_source"),
    *_floats("multiplier", "tick_size", "round_lot", "leverage"),
    "is_etf bool",
    "is_test_issue bool",
    "optionable bool",
    "in_sp500 bool",
    "is_leveraged bool",
    "is_inverse bool",
    "listed_on date",
    "first_seen date",
    "delisted_on date",
)
# L1: which symbol each FIGI used and when (one full history per snapshot date).
SYMBOL_HISTORY = _fixed(
    "instruments/symbol_history",
    "reference",
    ("instrument_id", "ts", "figi", "symbol", "valid_from"),
    "instrument_id string!",
    "ts timestamp_utc!",
    *_strings("figi", "symbol"),
    "valid_from date",
    "valid_to date",
)
# L1: symbol id -> FIGI id upgrades (ADR 0018); cumulative, one full map per snapshot date.
ID_MAP = _fixed(
    "instruments/id_map",
    "reference",
    ("instrument_id", "ts", "old_id", "new_id", "symbol", "effective", "known_at"),
    "instrument_id string!",
    "ts timestamp_utc!",
    *_strings("old_id", "new_id", "symbol"),
    "effective date",
    "known_at timestamp_utc",
)
# L1: company details from SEC EDGAR, per instrument (one full snapshot per date).
INSTRUMENT_COMPANY = _fixed(
    "instruments/company",
    "reference",
    ("instrument_id", "symbol", "cik", "name", "sic", "sector", "fetched_on"),
    "instrument_id string!",
    *_strings("symbol", "cik", "cik_source", "name", "entity_type", "sic", "sic_description"),
    *_strings("sic_division", "sector", "industry", "state_of_incorporation", "fiscal_year_end"),
    *_strings("website", "former_names", "exchanges", "tickers"),
    "fetched_on date",
)
# L2: the Treasury par yield curve, one partition per curve date, one row per tenor
# (``instrument_id`` = ``RATE:UST-<tenor>``). Rates are decimals; ADR 0021 has the conventions.
TREASURY_RATES = _fixed(
    "rates/treasury",
    "curve",
    ("instrument_id", "ts", "tenor", "tenor_days", "rate_par", "rate_cont"),
    "instrument_id string!",
    "ts timestamp_utc!",
    "tenor string!",
    "tenor_days int64!",
    "rate_par float64!",
    "rate_cont float64!",
)
# L2: OHLCV bars; the table name carries the interval, e.g. "bars/1d", "bars/5m".
BAR_INTERVALS = frozenset({"1d", "1h", "30m", "15m", "5m", "1m"})
BAR_COLUMNS = ("instrument_id", "ts", "open", "high", "low", "close", "volume")
_BAR_TYPES = (
    "instrument_id string!",
    "ts timestamp_utc!",
    *(f"{c} float64!" for c in FIELDS),
    *_floats("vwap", "trades"),
)

KNOWN: dict[str, TableSpec] = {
    t.name: t
    for t in (
        UNIVERSE,
        UNDERLYING_QUOTES,
        OPTION_QUOTES,
        CHAIN_STATUS,
        INSTRUMENT_REFERENCE,
        SYMBOL_HISTORY,
        ID_MAP,
        INSTRUMENT_COMPANY,
        TREASURY_RATES,
    )
}
# Open-ended tables: the producing rollup, event source, catalogue or screener defines the
# columns beyond instrument_id (+ ts for events).
OPEN_PREFIXES = {
    "rollups/daily/": "rollup",
    "rollups/instrument/": "rollup",
    "events/": "event",
    "results/": "results",
    "catalog/": "catalog",
}


def spec_for(table: str) -> TableSpec:
    if table in KNOWN:
        return KNOWN[table]
    if table.startswith("bars/"):
        interval = table.removeprefix("bars/")
        if interval not in BAR_INTERVALS:
            raise DataValidationError(table, [f"unknown bar interval {interval!r}"])
        return _fixed(table, "bar", BAR_COLUMNS, *_BAR_TYPES)
    for prefix, grain in OPEN_PREFIXES.items():
        if table.startswith(prefix) and len(table) > len(prefix):
            required = ("instrument_id", "ts") if grain == "event" else ("instrument_id",)
            keys = ("instrument_id string!", "ts timestamp_utc!")[: len(required)]
            return TableSpec(table, grain, required, open_ended=True, columns=_columns(*keys))
    raise DataValidationError(
        table, ["unknown table; add a TableSpec to storage/tables/schemas.py"]
    )


def validate_frame(table: str, frame: pd.DataFrame) -> None:
    spec = spec_for(table)
    missing = [c for c in (*COMMON, *spec.required) if c not in frame.columns]
    problems = [f"missing columns: {missing}"] if missing else []
    if not spec.open_ended:
        undeclared = [c for c in frame.columns if spec.column(str(c)) is None]
        if undeclared:
            problems.append(
                f"undeclared columns {undeclared}: declare them in storage/tables/schemas.py"
            )
    if not missing:
        if frame[list(COMMON)].isna().to_numpy().any():
            problems.append("point-in-time columns contain nulls")
        if frame["instrument_id"].isna().any():
            problems.append("null instrument_id")
        if frame.duplicated(subset=_key(spec, frame)).any():
            problems.append("duplicate rows for the table key")
        if spec.grain == "bar":
            problems.extend(bar_problems(frame))
    if problems:
        raise DataValidationError(table, problems)


def _key(spec: TableSpec, frame: pd.DataFrame) -> list[str]:
    key = ["instrument_id"]
    if "ts" in frame.columns and spec.grain != "universe":  # history rows: one per (id, from)
        key.append("ts")
    if spec.grain == "event" and "change" in frame.columns:  # several kinds of change per day
        key.append("change")
    return key


def bar_problems(frame: pd.DataFrame) -> list[str]:
    """OHLCV sanity checks on a bars frame (``core.validation.bars.ohlcv_problems``)."""
    return ohlcv_problems(*(frame[col].to_numpy(dtype=np.float64) for col in FIELDS))
