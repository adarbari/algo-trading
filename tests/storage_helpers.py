"""Builders for stamped frames used across storage, service and app tests."""

from datetime import UTC, date, datetime

import pandas as pd

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
