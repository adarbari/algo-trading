"""Builders for stamped frames used across storage, service and app tests."""

from collections.abc import Mapping
from datetime import UTC, date, datetime

import pandas as pd

from algotrade.storage.tables.writers import StoreWriter

T0 = datetime(2026, 10, 2, 22, 0, tzinfo=UTC)


def stamped(
    rows: list[dict[str, object]],
    session: date,
    run_id: str,
    knowledge: datetime = T0,
    source: str = "test",
) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["session_date"] = session
    frame["knowledge_ts"] = pd.Timestamp(knowledge)
    frame["source"] = source
    frame["run_id"] = run_id
    return frame


def universe_rows(symbols: list[str], **overrides: object) -> list[dict[str, object]]:
    return [
        {
            "instrument_id": f"EQ:{s}",
            "symbol": s,
            "security_type": "COMMON_STOCK",
            "asset_class": "STOCK",
            "company_name": f"{s} Inc",
            "exchange": "NASDAQ",
            "optionable": True,
            "status": "ACTIVE",
            "universe_version": "v1",
            "last_verified": "2026-10-01",
            **overrides,
        }
        for s in symbols
    ]


def reference_rows(universe: list[dict[str, object]]) -> list[dict[str, object]]:
    """L1 ``instruments/reference`` rows matching ``universe_rows`` (as the import writes them)."""
    return [
        {
            "instrument_id": u["instrument_id"],
            "symbol": u["symbol"],
            "asset_class": "EQ",
            "security_type": u["security_type"],
            "multiplier": 1.0,
            "status": u["status"],
            "optionable": u["optionable"],
            "is_etf": u["security_type"] == "ETF",
        }
        for u in universe
    ]


def write_reference(
    writer: StoreWriter, session: date, ids: Mapping[str, str], run_id: str = "ref"
) -> None:
    """An ``instruments/reference`` snapshot mapping symbol -> id (all active equities)."""
    rows = [
        {
            "instrument_id": iid,
            "symbol": symbol,
            "asset_class": "EQ",
            "security_type": "COMMON_STOCK",
            "multiplier": 1.0,
            "status": "ACTIVE",
        }
        for symbol, iid in ids.items()
    ]
    writer.write_table("instruments/reference", session, run_id, stamped(rows, session, run_id))


def holdings_rows(
    fund: str,
    as_of: date,
    lines: list[tuple[str | None, str, float]],
    total: int | None = None,
    linked: Mapping[str, str] | None = None,
) -> list[dict[str, object]]:
    """``holdings/etf`` rows of one fund: ``lines`` are (ticker, name, weight) largest first;
    ``linked`` maps a ticker to the instrument id it resolves to."""
    return [
        {
            "instrument_id": fund, "symbol": fund.removeprefix("EQ:"), "as_of": as_of,
            "rank": rank, "holding_symbol": ticker,
            "holding_id": (linked or {}).get(ticker) if ticker else None,
            "holding_name": name, "weight": weight, "asset_class": "Equity",
            "sector": None, "shares": 100.0 * rank, "identifier": f"CUSIP{rank:04d}",
            "holdings_count": total or len(lines),
        }
        for rank, (ticker, name, weight) in enumerate(lines, start=1)
    ]  # fmt: skip
