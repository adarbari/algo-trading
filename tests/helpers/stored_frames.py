"""Builders for stamped frames used across storage, service and app tests."""

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from algotrade.data import StoreReader
from algotrade.storage.backends.local import LocalBackend
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
    core: int,
    core_stale: int,
    rest: int,
    rest_stale: int,
    fetch_errors: int = 0,
    *,
    chain_day: str = "2026-10-01",
) -> list[dict[str, object]]:
    """``chains/status`` rows: ``core`` core names (the first ``core_stale`` STALE_DATA, the
    chain served for ``chain_day``) and ``rest`` rest names (the first ``rest_stale`` stale), then
    ``fetch_errors`` more rest names that failed to fetch. Symbols are ``C<i>`` / ``R<i>`` /
    ``E<i>``."""
    spec = (("C", "core", core, core_stale), ("R", "rest", rest, rest_stale))
    rows = [
        {
            "instrument_id": f"EQ:{prefix}{i}",
            "symbol": f"{prefix}{i}",
            "tier": tier,
            "status": f"STALE_DATA: chain is for {chain_day}" if i < stale else "OK",
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


type StatementFact = tuple[
    str, str, str, date, date, date, float
]  # id, concept, tag, start, end, filed, value
STATEMENT_COLUMNS = [
    "instrument_id",
    "concept",
    "tag",
    "period_start",
    "period_end",
    "filed",
    "value",
]


def statement_frame(facts: list[StatementFact]) -> pd.DataFrame:
    """``instruments/statements`` facts as a statement group reads them (tag without prefix)."""
    rows = [(i, c, f"us-gaap:{t}", s, e, f, v) for i, c, t, s, e, f, v in facts]
    return pd.DataFrame(rows, columns=STATEMENT_COLUMNS)


def quarter_facts(
    instrument: str, concept: str, tag: str, values: list[float], first_end: date, lag: int = 40
) -> list[StatementFact]:
    """Consecutive discrete three-month facts ending ``first_end`` and every ~91 days after,
    each filed ``lag`` days after its end."""
    out = []
    for n, value in enumerate(values):
        end = first_end + timedelta(days=91 * n)
        out.append(
            (
                instrument,
                concept,
                tag,
                end - timedelta(days=89),
                end,
                end + timedelta(days=lag),
                value,
            )
        )
    return out


def publish(backend: MemoryBackend | LocalBackend, run: str, table: str, *days: date) -> None:
    writer = StoreWriter(backend)
    for day in days:
        frame = stamped([{"instrument_id": "EQ:A", "value": 1.0}], day, run)
        writer.write_table(table, day, run, frame, pending=True)
    backend.tables.commit_run(run, T0 + timedelta(minutes=5))


def screen_values_rows(
    instruments: int, per: int = 3, user: str = "site"
) -> list[dict[str, object]]:
    """``results/rule_screen_values`` rows of one config, instruments in a fixed shuffled order
    (what an unclustered writer stored): ``per`` criterion rows each."""
    order = sorted(range(instruments), key=lambda n: (n * 7919) % instruments)
    return [
        {
            "instrument_id": f"EQ:{n:05d}",
            "user_id": user,
            "config_id": "cfg",
            "criterion_id": f"c{k}",
            "field": "price",
            "mode": "criterion",
            "outcome": "PASS",
            "value_num": float(n * 10 + k),
        }
        for n in order
        for k in range(per)
    ]


def screen_rows(instruments: int, user: str = "site") -> list[dict[str, object]]:
    """``results/rule_screen`` rows of one config, in the same shuffled instrument order."""
    order = sorted(range(instruments), key=lambda n: (n * 7919) % instruments)
    return [
        {
            "instrument_id": f"EQ:{n:05d}",
            "user_id": user,
            "config_id": "cfg",
            "config_hash": "h",
            "decision": "PICK" if n % 2 else "DROP",
            "rank": n,
            "score": float(n),
        }
        for n in order
    ]


def make_unclustered(directory: Path) -> None:
    """Rewrite every data file under ``directory`` as the writer did before row groups were
    clustered: its rows out of instrument order, one big group (a store from before the change)."""
    for path in directory.glob("run=*.parquet"):
        data = pq.read_table(path)
        data = data.take(list(range(data.num_rows))[::-1])  # not in instrument order
        pq.write_table(data, path, compression="zstd", row_group_size=1 << 20)


def structure_pnl_row(
    instrument: str = "EQ:A",
    key: str = "k",
    session: date = date(2026, 10, 5),
    hold: int = 5,
    **overrides: object,
) -> dict[str, object]:
    """One COMPLETE ``structure_pnl@v2`` row (a short put held to its horizon) with every
    required column; ``overrides`` replace any column."""
    row: dict[str, object] = {
        "instrument_id": instrument, "ts": pd.Timestamp(session, tz="UTC"), "position_key": key,
        "price_source": "cboe", "licence": "open", "window_end": date(2026, 10, 12),
        "hold_sessions": hold, "leg_kinds": ["option"], "leg_contract_ids": ["OPT:A"],
        "leg_rights": ["P"], "leg_strikes": [95.0], "leg_expiries": [date(2026, 11, 20)],
        "leg_qty": [-1.0], "leg_entry_mid": [2.0], "leg_entry_half_spread": [0.05],
        "leg_entry_delta": [-0.3], "entry_spot": 100.0, "entry_net_mid": -2.0,
        "entry_half_spread": 0.05, "collateral": 95.0, "notional": 100.0,
        "exit_session": date(2026, 10, 12), "exit_kind": "HORIZON", "exit_basis": "QUOTE",
        "exit_net_mid": -1.5, "exit_half_spread": 0.05, "expired_otm": False,
        "exit_unknown_closes": 0, "pnl_mid": 0.5, "option_pnl": 0.5, "stock_pnl": 0.0,
        "outcome_status": "COMPLETE", "outcome_reason": None,
        **overrides,
    }  # fmt: skip
    return row
