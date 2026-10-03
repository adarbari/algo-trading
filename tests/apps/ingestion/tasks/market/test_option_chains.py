from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.derived.rollups import compute_rollups
from algotrade_ingestion.tasks.market.option_chains import (
    OPTIONS,
    STATUS,
    ChainJobConfig,
    Underlying,
    ingest_option_chains,
    prioritise,
)
from algotrade_ingestion.tasks.reference.universe_import import UniverseFile, import_universe
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.framework.limiter import Limiter, Pacing
from algotrade_sources.vendors.cboe.option_chains import URL, CboeOptionsSource
from tests.helpers.ingest_fakes import CountingLimiter, http_for, task_ctx
from tests.helpers.payloads import cboe as fx
from tests.helpers.stored_frames import stamped, write_reference

DAY = fx.SESSION
CLOCK = lambda: datetime(2026, 10, 2, 22, 0, tzinfo=UTC)  # noqa: E731
NO_RETRY = RetryPolicy(tries=1, base_delay=0, max_delay=0)


class FakeFeed:
    """Serves fixture payloads by symbol; counts calls; can fail a symbol N times."""

    def __init__(
        self, payloads: dict[str, bytes | Exception], fail_first: dict[str, int] | None = None
    ):
        self.payloads, self.fail_first, self.calls = payloads, dict(fail_first or {}), []

    def __call__(self, url: str) -> bytes:
        symbol = url.removeprefix(URL.split("{")[0]).removesuffix(".json")
        self.calls.append(symbol)
        if self.fail_first.get(symbol, 0) > 0:
            self.fail_first[symbol] -= 1
            raise HttpError(503)
        outcome = self.payloads.get(symbol, HttpError(404))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def universe(*symbols: str) -> list[Underlying]:
    return [Underlying(f"EQ:{s}", s) for s in symbols]


def run(  # type: ignore[no-untyped-def]
    writer: StoreWriter,
    feed: FakeFeed,
    symbols: list[Underlying],
    limiter: CountingLimiter | None = None,
    **config: float,
):
    source = CboeOptionsSource(http_for(feed, NO_RETRY, limiter))
    return ingest_option_chains(
        task_ctx(writer, clock=CLOCK),
        source,
        symbols,
        DAY,
        ChainJobConfig(**config),  # type: ignore[arg-type]
    )


def test_chain_job_records_every_status_and_publishes() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    feed = FakeFeed(
        {
            "GOOD": fx.payload("GOOD"),
            "OLD": fx.payload("OLD", session=DAY - timedelta(days=1)),
            "BARE": fx.payload("BARE", options=[fx.contract("BARE1", fx.EXPIRIES[0], "C", 100)]),
            "EMPTY": fx.payload("EMPTY", options=[]),
            "BROKEN": HttpError(500),
        }
    )
    record = run(
        writer, feed, universe("GOOD", "OLD", "BARE", "EMPTY", "BROKEN", "GONE"), retry_pause_s=0
    )
    assert record.items == {
        "EQ:GOOD": "OK",
        "EQ:OLD": "STALE_DATA: chain is for 2026-10-01",
        "EQ:BARE": "NO_STANDARD_SERIES",
        "EQ:EMPTY": "NO_CHAIN",
        "EQ:BROKEN": record.items["EQ:BROKEN"],
        "EQ:GONE": "NO_CHAIN",
    }
    assert record.items["EQ:BROKEN"].startswith("FETCH_ERROR")
    assert record.status is RunStatus.PARTIAL
    assert feed.calls.count("BROKEN") == 2  # main pass + gentle retry pass
    status = reader.table(STATUS, DAY)
    assert status is not None and len(status) == 6
    options = reader.table(OPTIONS, DAY)
    assert options is not None and set(options["underlying_id"]) == {"EQ:GOOD"}
    assert backend.raw.get("cboe_delayed", "option_chain", DAY, record.run_id, "GOOD") is not None


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> MemoryBackend | LocalBackend:
    return MemoryBackend() if request.param == "memory" else LocalBackend(tmp_path)


def test_chain_job_resumes_and_retries(backend: MemoryBackend | LocalBackend) -> None:
    writer = StoreWriter(backend)
    feed = FakeFeed({"A": fx.payload("A"), "B": fx.payload("B")}, fail_first={"B": 2})
    limiter = CountingLimiter()
    first = run(writer, feed, universe("A", "B"), limiter, retry_pause_s=7)
    assert first.status is RunStatus.PARTIAL
    assert limiter.held == 7  # the retry pass waited out a shared cool-down first
    assert writer.staging.keys(first.run_id, OPTIONS) == ["A"]  # FETCH_ERROR left: kept
    second = run(writer, feed, universe("A", "B"), retry_pause_s=0)
    assert second.run_id == first.run_id
    assert second.status is RunStatus.COMPLETE
    assert feed.calls.count("A") == 1  # finished tickers are not fetched again
    options = StoreReader(backend).table(OPTIONS, DAY)
    assert options is not None and set(options["underlying_id"]) == {"EQ:A", "EQ:B"}
    assert writer.staging.keys(second.run_id, OPTIONS) == []  # resume completed: dropped


def test_finished_chain_runs_drop_their_staging(backend: MemoryBackend | LocalBackend) -> None:
    writer = StoreWriter(backend)
    done = run(writer, FakeFeed({"A": fx.payload("A")}), universe("A"), retry_pause_s=0)
    assert done.status is RunStatus.COMPLETE
    assert writer.staging.keys(done.run_id, OPTIONS) == []
    assert StoreReader(backend).table(OPTIONS, DAY) is not None
    # PARTIAL with nothing a resume would refetch (no FETCH_ERROR): dropped too
    stale = {"A": fx.payload("A"), "OLD": fx.payload("OLD", session=DAY - timedelta(days=1))}
    partial = run(writer, FakeFeed(stale), universe("A", "OLD"), retry_pause_s=0)
    assert partial.status is RunStatus.PARTIAL
    assert writer.staging.keys(partial.run_id, OPTIONS) == []


def test_mass_no_chain_is_suspicious() -> None:
    writer = StoreWriter(MemoryBackend())
    record = run(writer, FakeFeed({"A": fx.payload("A")}), universe("A", "X", "Y"), retry_pause_s=0)
    assert record.status is RunStatus.PARTIAL
    assert "returned no chain" in record.stats["partial"][0]


TABLE = "rollups/instrument/option_liquidity@v1"


def test_rollups_task_scores_liquidity() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    deep = fx.payload("DEEP", options=fx.chain("DEEP", spread=0.02, oi=5000))
    feed = FakeFeed(
        {"DEEP": deep, "THIN": fx.payload("THIN", options=fx.chain("THIN", spread=1.5, oi=3))}
    )
    run(writer, feed, universe("DEEP", "THIN", "GONE"), retry_pause_s=0)
    ctx = task_ctx(writer, reader, CLOCK)
    record = compute_rollups(ctx, DAY, only=["option_liquidity@v1"])
    assert record.items == {"option_liquidity@v1": "OK: 1 sessions, 3 rows"}
    frame = reader.table(TABLE, DAY)
    assert frame is not None
    assert frame["liq_status"].value_counts().to_dict() == {"OK": 2, "NO_CHAIN": 1}
    rows = frame.set_index("instrument_id")
    assert rows.loc["EQ:DEEP", "put_tier"] == "A"
    assert rows.loc["EQ:THIN", "put_tier"] == "D"
    assert rows.loc["EQ:DEEP", "target_expiry"] == date(2026, 11, 20)
    assert rows.loc["EQ:DEEP", "iv30"] == 42.0


def test_universe_import(tmp_path: Path) -> None:
    stocks = tmp_path / "stocks.csv"
    stocks.write_text(
        "ticker,company_name,security_type,status,optionable\n"
        "aapl,Apple,,ACTIVE,TRUE\nQURE,uniQure,ADR,,\nAAPL,dup,,,\n,blank,,,\n"
        "OLD,Old Co,COMMON_STOCK,DELISTED,FALSE\n"
    )
    etfs = tmp_path / "etfs.csv"
    etfs.write_text("ticker,notes\nTQQQ,leveraged\n")
    backend = MemoryBackend()
    write_reference(StoreWriter(backend), DAY, {"AAPL": "EQ:BBG000B9XRY4"})
    record = import_universe(
        task_ctx(StoreWriter(backend), StoreReader(backend), CLOCK),
        [UniverseFile(stocks, "STOCK"), UniverseFile(etfs, "ETF")],
        "2026-10",
        DAY,
    )
    assert record.stats["rows_loaded"] == 5
    assert record.stats["duplicates_removed"] == 1
    assert record.stats["inactive_or_unoptionable"] == 1
    assert record.stats["by_security_type"] == {"COMMON_STOCK": 2, "ADR": 1, "ETF": 1}
    frame = StoreReader(backend).table("universe", DAY)
    assert frame is not None
    assert set(frame["universe_version"]) == {"2026-10"}
    ids = dict(zip(frame["symbol"], frame["instrument_id"], strict=True))
    assert (ids["AAPL"], ids["QURE"]) == ("EQ:BBG000B9XRY4", "EQ:QURE")  # known keeps its id


def test_universe_import_requires_ticker(tmp_path: Path) -> None:
    from algotrade.core.model.errors import DataValidationError  # noqa: PLC0415

    bad = tmp_path / "bad.csv"
    bad.write_text("symbol\nAAPL\n")
    with pytest.raises(DataValidationError, match="ticker"):
        backend = MemoryBackend()
        import_universe(
            task_ctx(StoreWriter(backend), StoreReader(backend), CLOCK),
            [UniverseFile(bad, "STOCK")],
            "v",
            DAY,
        )


PRICE_STATS = "rollups/instrument/price_stats@v2"
OPTION_LIQ = "rollups/instrument/option_liquidity@v1"


def _rows(day: date, run_id: str, rows: list[dict[str, object]]) -> pd.DataFrame:
    return stamped(rows, day, run_id)


def test_prioritise_orders_by_priority_sp500_liquidity_then_alphabetically() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    symbols = ["AAA", "BBB", "MSFT", "AAPL", "QQQ", "SPY", "LOWX", "HIGH1", "HIGH2", "MED", "UNK"]
    reference = [
        {"instrument_id": f"EQ:{s}", "symbol": s, "asset_class": "EQ", "multiplier": 1.0,
         "security_type": "ETF" if s in ("SPY", "QQQ") else "COMMON_STOCK", "status": "ACTIVE",
         "in_sp500": s in ("MSFT", "AAPL")}
        for s in symbols
    ]  # fmt: skip
    writer.write_table("instruments/reference", DAY, "ref", _rows(DAY, "ref", reference))
    big, ok = {"adv_usd_20d": 2e8, "close": 50.0}, {"liq_status": "OK"}
    tier_a = {**ok, "put_tier": "A", "call_tier": "A", "chain_volume": 9000}
    tier_b = {**ok, "put_tier": "B", "call_tier": "B", "chain_volume": 100}
    rows = {  # symbol -> (price_stats@v2 row, option_liquidity@v1 row)
        "HIGH1": (big, {**tier_a, "chain_oi": 60_000}),
        "HIGH2": (big, {**tier_a, "chain_oi": 90_000}),
        "MED": ({"adv_usd_20d": 2e7, "close": 20.0}, {**tier_b, "chain_oi": 6_000}),
        "LOWX": ({"adv_usd_20d": 1e6, "close": 3.0}, {**ok, "put_tier": "D", "chain_oi": 1}),
        "UNK": (big, {"liq_status": "FETCH_ERROR"}),  # the fetch failed: UNKNOWN
        "MSFT": (big, {**tier_a, "chain_oi": 60_000}),  # HIGH
        "AAPL": ({"adv_usd_20d": 2e7, "close": 20.0}, {**tier_b, "chain_oi": 6_000}),  # MEDIUM
    }
    yesterday = DAY - timedelta(days=1)
    prices = [{"instrument_id": f"EQ:{s}", **p} for s, (p, _) in rows.items()]
    options = [{"instrument_id": f"EQ:{s}", **o} for s, (_, o) in rows.items()]
    writer.write_table(PRICE_STATS, yesterday, "r1", _rows(yesterday, "r1", prices))
    writer.write_table(OPTION_LIQ, yesterday, "r1", _rows(yesterday, "r1", options))
    later = DAY + timedelta(days=1)  # after the session: never used
    aaa = [{"instrument_id": "EQ:AAA", **big}]
    writer.write_table(PRICE_STATS, later, "r2", _rows(later, "r2", aaa))
    ordered, tiers = prioritise(reader, DAY, universe(*symbols), ["spy", "QQQ", "NOPE"])
    assert [u.symbol for u in ordered] == [
        "SPY", "QQQ",  # configured priority, in its order
        "MSFT", "AAPL",  # S&P 500 by liquidity class
        "HIGH2", "HIGH1", "MED", "LOWX", "UNK",  # class, then chain OI descending
        "AAA", "BBB",  # the rest, alphabetically
    ]  # fmt: skip
    assert tiers == {"priority": 4, "liquidity": 5, "rest": 2}
    # an empty store: everything alphabetical, except the configured priority
    bare, tiers = prioritise(StoreReader(MemoryBackend()), DAY, universe("B", "A", "SPY"), ["SPY"])
    assert [u.symbol for u in bare] == ["SPY", "A", "B"]
    assert tiers == {"priority": 1, "liquidity": 0, "rest": 2}


def test_chain_run_fetches_in_priority_order_and_records_tiers_and_pacing(
    tmp_path: Path,
) -> None:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    feed = FakeFeed({"SPY": fx.payload("SPY"), "B": fx.payload("B")})
    limiter = Limiter("cboe", Pacing(0.0), tmp_path)
    source = CboeOptionsSource(http_for(feed, NO_RETRY, limiter))
    ctx = task_ctx(writer, clock=CLOCK)
    ctx.pacing = {"cboe": limiter, "idle": Limiter("idle", 0.0, tmp_path)}
    config = ChainJobConfig(workers=1, retry_pause_s=0, priority_symbols=("SPY",))
    record = ingest_option_chains(ctx, source, universe("B", "A", "SPY"), DAY, config)
    assert feed.calls == ["SPY", "A", "B"]
    assert record.stats["order_tiers"] == {"priority": 1, "liquidity": 0, "rest": 2}
    pacing = record.stats["pacing"]
    assert set(pacing) == {"cboe"}  # keys that sent no request are left out
    assert pacing["cboe"]["requests"] == 3 and pacing["cboe"]["errors"] == 0  # A: 404, missing
