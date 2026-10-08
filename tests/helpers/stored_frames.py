"""Builders for stamped frames used across storage, service and app tests."""

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
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
    filed: date | None = None,
) -> list[dict[str, object]]:
    """``holdings/etf`` rows of one fund: ``lines`` are (ticker, name, weight) largest first;
    ``linked`` maps a ticker to the instrument id it resolves to."""
    return [
        {
            "instrument_id": fund, "symbol": fund.removeprefix("EQ:"), "as_of": as_of,
            "rank": rank, "holding_symbol": ticker,
            "holding_id": (linked or {}).get(ticker) if ticker else None,
            "holding_name": name, "weight": weight, "asset_class": "Equity",
            "sector": None, "shares": 100.0 * rank, "identifier": f"9000000{rank:02d}",
            "filed": filed,
            "holdings_count": total or len(lines),
        }
        for rank, (ticker, name, weight) in enumerate(lines, start=1)
    ]  # fmt: skip


def chain_status_rows(
    core: int, core_stale: int, rest: int, rest_stale: int, fetch_errors: int = 0
) -> list[dict[str, object]]:
    """``chains/status`` rows: ``core`` core names (the first ``core_stale`` STALE_DATA) and
    ``rest`` rest names (the first ``rest_stale`` stale), then ``fetch_errors`` more rest names
    that failed to fetch. Symbols are ``C<i>`` / ``R<i>`` / ``E<i>``."""
    spec = (("C", "core", core, core_stale), ("R", "rest", rest, rest_stale))
    rows = [
        {
            "instrument_id": f"EQ:{prefix}{i}",
            "symbol": f"{prefix}{i}",
            "tier": tier,
            "status": "STALE_DATA: chain is for 2026-10-01" if i < stale else "OK",
        }
        for prefix, tier, total, stale in spec
        for i in range(total)
    ]
    rows += [
        {
            "instrument_id": f"EQ:E{i}",
            "symbol": f"E{i}",
            "tier": "rest",
            "status": "FETCH_ERROR: timeout",
        }
        for i in range(fetch_errors)
    ]
    return rows


def seed_chain_screen(
    session: date, status: list[dict[str, object]]
) -> tuple[StoreReader, StoreWriter]:
    """A store a ``short_premium_liquidity`` screen runs over: the universe is the names of
    ``status`` (``chain_status_rows``), each with an option-liquidity row (``STALE_DATA`` as its
    ``liq_status`` where its chain is stale, as the rollup copies it), and ``chains/status``."""
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    symbols = [str(r["symbol"]) for r in status]
    universe = universe_rows(symbols, last_verified=session.isoformat())
    snapshot = session - timedelta(days=2)
    writer.write_table("universe", snapshot, "u1", stamped(universe, session, "u1"))
    writer.write_table(
        "instruments/reference", snapshot, "u1", stamped(reference_rows(universe), session, "u1")
    )
    features = [
        {
            "instrument_id": r["instrument_id"],
            "liq_status": r["status"],
            "put_tier": "A",
            "call_tier": "B",
            "short_put_ok": True,
            "short_call_ok": True,
        }
        for r in status
    ]
    writer.write_table(
        "rollups/instrument/option_liquidity@v1", session, "f1", stamped(features, session, "f1")
    )
    writer.write_table("chains/status", session, "c1", stamped(status, session, "c1"))
    return StoreReader(backend), writer
