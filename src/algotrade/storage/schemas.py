"""Canonical table schemas: the data contract every writer must satisfy.

Every row carries the point-in-time columns (ADR 0007). Market tables also carry ``ts``.
Feature and result tables are open-ended: they need the common columns plus
``instrument_id``; the rest is defined by the feature or screener that produces them.
"""

from dataclasses import dataclass

import pandas as pd

from algotrade.core.errors import DataValidationError

SCHEMA_VERSION = 1
COMMON = ("session_date", "knowledge_ts", "source", "run_id")


@dataclass(frozen=True)
class TableSpec:
    name: str
    grain: str
    required: tuple[str, ...]
    open_ended: bool = False


UNIVERSE = TableSpec(
    "universe",
    "universe",
    ("instrument_id", "symbol", "security_type", "optionable", "status", "universe_version"),
)
UNDERLYING_QUOTES = TableSpec(
    "chains/underlying_quotes",
    "chain_snapshot",
    ("instrument_id", "symbol", "ts", "price", "close", "volume", "iv30"),
)
OPTION_QUOTES = TableSpec(
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
)
CHAIN_STATUS = TableSpec("chains/status", "chain_snapshot", ("instrument_id", "status"))

# L1: what each instrument is (one full snapshot per date). See docs/design/phase-0.md.
INSTRUMENT_REFERENCE = TableSpec(
    "instruments/reference",
    "reference",
    ("instrument_id", "symbol", "asset_class", "security_type", "multiplier", "status"),
)
# L2: OHLCV bars; the table name carries the interval, e.g. "bars/1d", "bars/5m".
BAR_INTERVALS = frozenset({"1d", "1h", "30m", "15m", "5m", "1m"})
BAR_COLUMNS = ("instrument_id", "ts", "open", "high", "low", "close", "volume")

KNOWN: dict[str, TableSpec] = {
    t.name: t
    for t in (UNIVERSE, UNDERLYING_QUOTES, OPTION_QUOTES, CHAIN_STATUS, INSTRUMENT_REFERENCE)
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
        return TableSpec(table, "bar", BAR_COLUMNS)
    for prefix, grain in OPEN_PREFIXES.items():
        if table.startswith(prefix) and len(table) > len(prefix):
            required = ("instrument_id", "ts") if grain == "event" else ("instrument_id",)
            return TableSpec(table, grain, required, open_ended=True)
    raise DataValidationError(table, ["unknown table; add a TableSpec to storage/schemas.py"])


def validate_frame(table: str, frame: pd.DataFrame) -> None:
    spec = spec_for(table)
    missing = [c for c in (*COMMON, *spec.required) if c not in frame.columns]
    problems = [f"missing columns: {missing}"] if missing else []
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
    if "ts" in frame.columns and spec.grain != "universe":
        key.append("ts")
    return key


def bar_problems(frame: pd.DataFrame) -> list[str]:
    """OHLCV sanity checks. Bad bars silently produce great-looking backtests."""
    problems: list[str] = []
    prices = frame[["open", "high", "low", "close"]]
    if prices.isna().to_numpy().any() or frame["volume"].isna().any():
        problems.append("bars contain NaN prices or volume")
        return problems
    if (prices <= 0).to_numpy().any():
        problems.append("non-positive prices")
    if (frame["volume"] < 0).any():
        problems.append("negative volume")
    if (frame["high"] < frame[["open", "close"]].max(axis=1)).any():
        problems.append("high below open/close")
    if (frame["low"] > frame[["open", "close"]].min(axis=1)).any():
        problems.append("low above open/close")
    return problems
