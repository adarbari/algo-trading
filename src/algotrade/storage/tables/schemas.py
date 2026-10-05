"""Canonical table schemas: the data contract every writer must satisfy.

Every row carries the point-in-time columns (ADR 0007). Market tables also carry ``ts``.
Fixed tables declare every column with an abstract type (``COLUMN_TYPES``) and nullability;
storage backends cast writes to those types (and fail on uncastable data), stamp
``SCHEMA_VERSION`` and the table name into each file, and cast older files on read.
Feature, event, catalogue and result tables are open-ended: they need the common columns
plus ``instrument_id`` (+ ``ts`` for events), which are typed; the rest is defined by the
feature, event source or screener that produces them.

Each table also declares how its runs combine (``TableSpec.runs``, ``RUN_MODES``): a
``snapshot`` run is the partition's full contents (the latest run known at ``as_of`` replaces
the others); a ``merge`` run is a window or increment (reads union every run known at
``as_of``, the latest run's row winning per ``table_key``). Backends apply it
(``storage/backends/run_selection.py``).
"""

from collections.abc import Iterable
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
COLUMN_TYPES = frozenset({"string", "float64", "float32", "int64", "bool", "date", "timestamp_utc"})
# How a partition's runs combine on read: "snapshot" (each run is the whole partition; the
# latest known at as_of wins) or "merge" (each run is a window; the union, latest per key).
RUN_MODES = frozenset({"snapshot", "merge"})


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
    defines the rest). Writes cast to the declared types and fail on uncastable data.
    ``runs`` says how a partition's runs combine on read (``RUN_MODES``); ``key``, when set,
    is the table key (``table_key``) instead of the grain's default. ``retention_days``, when
    set, is the default retention window: only such tables may have old partitions purged
    (``purge_before``); every other table is history, kept forever."""

    name: str
    grain: str
    required: tuple[str, ...]
    open_ended: bool = False
    columns: tuple[Column, ...] = ()
    runs: str = "snapshot"
    key: tuple[str, ...] = ()
    retention_days: int | None = None

    def __post_init__(self) -> None:
        if self.runs not in RUN_MODES:
            raise ValueError(f"{self.name}: unknown run mode {self.runs!r}")

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


def _fixed(
    name: str,
    grain: str,
    required: tuple[str, ...],
    *columns: str,
    runs: str = "snapshot",
    key: tuple[str, ...] = (),
    retention_days: int | None = None,
) -> TableSpec:
    spec = TableSpec(
        name, grain, required, columns=_columns(*columns), runs=runs, key=key,
        retention_days=retention_days,
    )  # fmt: skip
    undeclared = [c for c in (*COMMON, *required, *key) if spec.column(c) is None]
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
    # FIGI review (ADR 0018): the vendor's FIGI when the build kept a different one or the
    # FIGI is shared, and the session that was first seen.
    "vendor_figi string",
    "figi_review_since date",
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
# L1: which symbol each FIGI used and when (the full history per snapshot date). Each build
# only opens and closes rows, so a session's runs merge per (figi, symbol, valid_from): a
# re-run that sees less can close a row (latest run wins) but never hide one.
SYMBOL_HISTORY = _fixed(
    "instruments/symbol_history",
    "reference",
    ("instrument_id", "ts", "figi", "symbol", "valid_from"),
    "instrument_id string!",
    "ts timestamp_utc!",
    *_strings("figi", "symbol"),
    "valid_from date",
    "valid_to date",
    runs="merge",
    key=("figi", "symbol", "valid_from"),
)
# L1: symbol id -> FIGI id upgrades (ADR 0018); cumulative, the full map per snapshot date.
# A session's runs merge per (old_id, new_id), so a run holding only its own upgrades can
# never hide the earlier ones (2026-10-03). Keyed on the pair, not old_id alone: a reused
# symbol id can upgrade again to another FIGI, and ``known_at`` tells the two apart.
ID_MAP = _fixed(
    "instruments/id_map",
    "reference",
    ("instrument_id", "ts", "old_id", "new_id", "symbol", "effective", "known_at"),
    "instrument_id string!",
    "ts timestamp_utc!",
    *_strings("old_id", "new_id", "symbol"),
    "effective date",
    "known_at timestamp_utc",
    runs="merge",
    key=("old_id", "new_id"),
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
# L1: share counts from SEC company facts, per instrument (every class of a CIK gets the
# CIK's facts). Runs are increments (new facts + a ``checked`` marker per fetched CIK), so
# they merge; a fact is identified by (instrument, concept, period end, filed date).
INSTRUMENT_SHARES = _fixed(
    "instruments/shares",
    "reference",
    ("instrument_id", "cik", "concept", "fetched_on"),
    "instrument_id string!",
    *_strings("symbol", "tag", "form", "accn", "fp"),
    "cik string!",
    "concept string!",
    "period_start date",
    "period_end date",
    "filed date",
    "fy int64",
    "shares float64",
    "class_values int64",
    "fetched_on date!",
    runs="merge",
    key=("instrument_id", "concept", "period_end", "filed"),
)
# L1: each instrument's IBKR stock contract (ADR 0028): conid and primary exchange from IB's
# contract lookup, one full snapshot per run (rows not refreshed are carried forward).
IBKR_CONTRACTS = _fixed(
    "instruments/ibkr_contracts",
    "reference",
    ("instrument_id", "symbol", "conid", "resolved_at"),
    "instrument_id string!",
    "symbol string!",
    "conid int64!",
    *_strings("primary_exchange", "sec_type", "currency"),
    "resolved_at date!",
)
# L2: IBKR's 30-day implied and historical vol of each underlying, one partition per session
# (ADR 0028). Runs merge per instrument (a backfill writes many sessions, the nightly one):
# the latest run's row wins. ``source_kind``: ``history`` (IB's daily bar) or ``snapshot``
# (the streamed value after the close). Licence: personal use (IBKR market data).
IBKR_IV30 = _fixed(
    "volatility/ibkr_iv30",
    "volatility",
    ("instrument_id", "iv30_ibkr", "source_kind"),
    "instrument_id string!",
    "symbol string",
    *_floats("iv30_ibkr", "hv30_ibkr"),
    "source_kind string!",
    runs="merge",
)
# Live option quotes the API read from IB Gateway (ADR 0028, the API's one write exception):
# every answer it served, one partition per session, a row per contract and time taken. Runs
# merge (each is a few snapshots; all are kept, keyed by contract and ``ts``). Written only
# through ``LiveWriter`` (``live/*``), never read by backtests. Licence: personal use.
LIVE_OPTION_QUOTES = _fixed(
    "live/option_quotes",
    "live",
    ("instrument_id", "underlying_id", "ts", "expiry", "right", "strike"),
    "instrument_id string!",
    "ts timestamp_utc!",
    "underlying_id string!",
    "symbol string",
    "expiry date!",
    "right string!",
    "strike float64!",
    *_floats("bid", "ask", "last", "close", "volume", "iv", "delta"),
    "conid int64",
    "market_data_type int64",
    runs="merge",
    retention_days=7,  # [sources] live_retention_days overrides the window
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
# L2: what an ETF holds (ADR 0035): one row per fund x holding x as-of date, the largest
# ``[etf_holdings] keep_top`` holdings of the fund's file, ranked by weight (1 = largest).
# ``as_of`` is the issuer's holdings date; the partition is the session of the run that read
# it. Runs are increments (a few funds each), so they merge on (fund, as_of, rank); a later
# run of the same as_of may hold fewer holdings, so readers take each fund's rows from its
# latest run (``data.funds.holdings``). ``weight`` is a fraction of the fund (negative for
# shorts); ``holding_id`` is the holding's instrument when its ticker resolves to a universe
# instrument; ``holdings_count`` counts every line of the issuer's file, not only those kept.
ETF_HOLDINGS = _fixed(
    "holdings/etf",
    "holdings",
    ("instrument_id", "as_of", "rank", "holding_name", "weight", "holdings_count"),
    "instrument_id string!",
    "symbol string",
    "as_of date!",
    "rank int64!",
    *_strings("holding_symbol", "holding_id"),
    "holding_name string!",
    "weight float64!",
    *_strings("asset_class", "sector", "identifier"),
    "shares float64",
    "holdings_count int64!",
    runs="merge",
    key=("instrument_id", "as_of", "rank"),
)
# Live verification (ADR 0026): our values vs another source's, one row per instrument and
# check for a session. ``status`` is PASS / WARN / FAIL / NA; ``diff`` is in the check's
# tolerance unit (relative or absolute, per ``note``).
VERIFICATION_IBKR = _fixed(
    "verification/ibkr",
    "verification",
    ("instrument_id", "symbol", "check", "status"),
    "instrument_id string!",
    *_strings("symbol", "note"),
    "check string!",
    "status string!",
    *_floats("ours", "theirs", "diff", "tolerance"),
    key=("instrument_id", "check"),
)
# Rule screens (ADR 0029): one fixed schema for every rule-screen config, so pages and Ideas
# query across screens. Many configs and users share a session's partition, so runs merge
# on (user, config, instrument): readers take a config's rows of its latest run (``run_id``
# from the run record), since a later run never removes rows an earlier one wrote.
RULE_SCREEN = _fixed(
    "results/rule_screen",
    "results",
    ("instrument_id", "user_id", "config_id", "config_hash", "decision", "rank"),
    "instrument_id string!",
    "user_id string!",
    "config_id string!",
    "config_version int64",
    "config_hash string!",
    "decision string!",
    "score float64",
    "rank int64!",
    "tie_break float64",
    *_strings("flags", "reasons", "failed", "near_missed", "missing"),
    runs="merge",
    key=("user_id", "config_id", "instrument_id"),
)
# One row per (instrument, criterion) and per display column (``mode = "column"``,
# ``outcome = "INFO"``): the value, PASS / NEAR / FAIL / MISSING, distance and penalty.
RULE_SCREEN_VALUES = _fixed(
    "results/rule_screen_values",
    "results",
    ("instrument_id", "user_id", "config_id", "criterion_id", "field", "mode", "outcome"),
    "instrument_id string!",
    "user_id string!",
    "config_id string!",
    "criterion_id string!",
    "field string!",
    "mode string!",
    "value_num float64",
    "value_str string",
    "outcome string!",
    *_floats("distance", "normalised", "penalty"),
    runs="merge",
    key=("user_id", "config_id", "instrument_id", "mode", "criterion_id"),
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
        INSTRUMENT_SHARES,
        TREASURY_RATES,
        VERIFICATION_IBKR,
        IBKR_CONTRACTS,
        IBKR_IV30,
        RULE_SCREEN,
        RULE_SCREEN_VALUES,
        LIVE_OPTION_QUOTES,
        ETF_HOLDINGS,
    )
}
# Open-ended tables: the producing rollup, event source, catalogue or screener defines the
# columns beyond instrument_id (+ ts for events). Event runs are windows (a backfill, then
# nightly -7..+30-day windows into the same session), so they merge; rollups, catalogues and
# results are full snapshots per run. Bars and chains (fixed, above) are snapshots too: a
# re-fetched session replaces the earlier fetch.
OPEN_PREFIXES = {
    "rollups/daily/": "rollup",
    "rollups/instrument/": "rollup",
    "events/": "event",
    "results/": "results",
    "catalog/": "catalog",
}


def result_table(name: str) -> str:
    """The table a result named ``name`` (a screener, a backtest output) is stored in."""
    return f"results/{name}"


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
            runs = "merge" if grain == "event" else "snapshot"
            return TableSpec(
                table, grain, required, open_ended=True, columns=_columns(*keys), runs=runs
            )
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
        if frame.duplicated(subset=table_key(spec, frame.columns)).any():
            problems.append("duplicate rows for the table key")
        if spec.grain == "bar":
            problems.extend(bar_problems(frame))
    if problems:
        raise DataValidationError(table, problems)


def table_key(spec: TableSpec, columns: Iterable[object]) -> list[str]:
    """The columns that identify a row: unique within a run (checked on write) and, for
    ``merge`` tables, the key the latest run wins on across runs. A spec's own ``key`` wins
    over the grain's default (``instrument_id``, + ``ts``, + ``change`` for events)."""
    if spec.key:
        return list(spec.key)
    present = {str(c) for c in columns}
    key = ["instrument_id"]
    if "ts" in present and spec.grain != "universe":  # history rows: one per (id, from)
        key.append("ts")
    if spec.grain == "event" and "change" in present:  # several kinds of change per day
        key.append("change")
    return key


def bar_problems(frame: pd.DataFrame) -> list[str]:
    """OHLCV sanity checks on a bars frame (``core.validation.bars.ohlcv_problems``)."""
    return ohlcv_problems(*(frame[col].to_numpy(dtype=np.float64) for col in FIELDS))


def require_retention(table: str) -> int:
    """``table``'s retention window; ``DataValidationError`` for a table kept forever (only
    tables that declare ``retention_days`` may have partitions purged)."""
    days = spec_for(table).retention_days
    if days is None:
        raise DataValidationError(table, ["no retention declared: its partitions are never purged"])
    return days
