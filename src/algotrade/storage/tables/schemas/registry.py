"""The table registry: ``KNOWN`` fixed specs, the open-ended prefixes, ``spec_for`` resolution, the
table key and retention lookup.
"""

from collections.abc import Iterable

from algotrade.core.model.errors import DataValidationError
from algotrade.storage.tables.edge_schemas import (
    EDGE_EVAL,
    EDGE_LEGS,
    EDGE_PAPER,
    EDGE_PICKS,
    EDGE_SERIES,
    EDGE_TRADES,
    EDGE_VERDICT,
    WINNERS_STUDY,
)
from algotrade.storage.tables.schemas.events import (
    ANALYST_ESTIMATE_SNAPSHOTS,
    ANALYST_VENDOR_ACCESS,
    EARNINGS_EVENTS,
    FILING_EVENTS,
    FILING_TEXT_EVENTS,
    FUND_NAV_EVENTS,
    INSIDER_EVENTS,
    IPO_LOCKUP_EVENTS,
    KNOWN_FROM,
    MACRO_RELEASE_EVENTS,
    MACRO_SERIES,
    SHORT_INTEREST_EVENTS,
    SHORT_VOLUME_EVENTS,
)
from algotrade.storage.tables.schemas.market import (
    _BAR_TYPES,
    BAR_COLUMNS,
    BAR_INTERVALS,
    CHAIN_STATUS,
    FUTURES_CURVE,
    IBKR_CONTRACTS,
    IBKR_IV30,
    LIVE_OPTION_QUOTES,
    OPTION_QUOTES,
    TREASURY_RATES,
    UNDERLYING_QUOTES,
    UNIVERSE,
    VERIFICATION_IBKR,
    VX_FUTURES,
)
from algotrade.storage.tables.schemas.outcomes import (
    OPTION_PNL_SPEC,
    OUTCOMES_PREFIX,
    outcomes_spec,
)
from algotrade.storage.tables.schemas.reference import (
    ETF_HOLDINGS,
    ETF_SHARES,
    ID_MAP,
    INDEX_MEMBERSHIP,
    INSTRUMENT_COMPANY,
    INSTRUMENT_DESCRIPTION,
    INSTRUMENT_REFERENCE,
    INSTRUMENT_SHARES,
    INSTRUMENT_STATEMENTS,
    LISTING_HISTORY,
    SYMBOL_HISTORY,
)
from algotrade.storage.tables.schemas.results import (
    FEEDBACK_DRAFTING_EVENTS,
    FEEDBACK_FEATURE_REQUESTS,
    RULE_SCREEN,
    RULE_SCREEN_VALUES,
    SCREEN_PICKS,
    SCREEN_RUNS,
    USAGE_LLM_CALLS,
)
from algotrade.storage.tables.spec import (
    TableSpec,
    columns_of,
    fixed,
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
        LISTING_HISTORY,
        INDEX_MEMBERSHIP,
        INSTRUMENT_COMPANY,
        INSTRUMENT_SHARES,
        INSTRUMENT_STATEMENTS,
        INSTRUMENT_DESCRIPTION,
        TREASURY_RATES,
        VERIFICATION_IBKR,
        IBKR_CONTRACTS,
        IBKR_IV30,
        VX_FUTURES,
        FUTURES_CURVE,
        RULE_SCREEN,
        RULE_SCREEN_VALUES,
        SCREEN_RUNS,
        SCREEN_PICKS,
        EDGE_EVAL,
        EDGE_SERIES,
        WINNERS_STUDY,
        EDGE_PAPER,
        EDGE_LEGS,
        EDGE_TRADES,
        EDGE_VERDICT,
        EDGE_PICKS,
        LIVE_OPTION_QUOTES,
        USAGE_LLM_CALLS,
        FEEDBACK_DRAFTING_EVENTS,
        FEEDBACK_FEATURE_REQUESTS,
        ETF_HOLDINGS,
        ETF_SHARES,
        MACRO_SERIES,
        ANALYST_VENDOR_ACCESS,
        ANALYST_ESTIMATE_SNAPSHOTS,
        EARNINGS_EVENTS,
        MACRO_RELEASE_EVENTS,
        FILING_EVENTS,
        FILING_TEXT_EVENTS,
        IPO_LOCKUP_EVENTS,
        SHORT_INTEREST_EVENTS,
        SHORT_VOLUME_EVENTS,
        FUND_NAV_EVENTS,
        INSIDER_EVENTS,
        OPTION_PNL_SPEC,
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
    "rollups/market/": "rollup",  # market-entity feature groups: one MKT:<market> row (ADR 0047)
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
        return fixed(table, "bar", BAR_COLUMNS, *_BAR_TYPES)
    if table.startswith(OUTCOMES_PREFIX) and len(table) > len(OUTCOMES_PREFIX):
        return outcomes_spec(table)
    for prefix, grain in OPEN_PREFIXES.items():
        if table.startswith(prefix) and len(table) > len(prefix):
            required = ("instrument_id", "ts") if grain == "event" else ("instrument_id",)
            keys = ("instrument_id string!", "ts timestamp_utc!")[: len(required)]
            event = grain == "event"
            typed = (*keys, f"{KNOWN_FROM} date") if event else keys
            runs = "merge" if event else "snapshot"
            return TableSpec(
                table, grain, required, open_ended=True, columns=columns_of(*typed), runs=runs
            )
    raise DataValidationError(
        table, ["unknown table; add a TableSpec to storage/tables/schemas.py"]
    )


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


def require_retention(table: str) -> int:
    """``table``'s retention window; ``DataValidationError`` for a table kept forever (only
    tables that declare ``retention_days`` may have partitions purged)."""
    days = spec_for(table).retention_days
    if days is None:
        raise DataValidationError(table, ["no retention declared: its partitions are never purged"])
    return days
