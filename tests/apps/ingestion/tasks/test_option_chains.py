from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from algotrade.data import StoreReader
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.sources.cboe import URL, CboeOptionsSource
from algotrade_ingestion.sources.http import HttpError, RetryPolicy
from algotrade_ingestion.tasks.features import TABLE, compute_option_liquidity
from algotrade_ingestion.tasks.option_chains import (
    OPTIONS,
    STATUS,
    ChainJobConfig,
    Underlying,
    ingest_option_chains,
)
from algotrade_ingestion.tasks.universe import UniverseFile, import_universe
from tests import cboe_fixture as fx
from tests.ingest_helpers import CountingLimiter, http_for, task_ctx
from tests.storage_helpers import write_reference

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


def test_chain_job_resumes_and_retries(tmp_path: Path) -> None:
    writer = StoreWriter(LocalBackend(tmp_path))
    feed = FakeFeed({"A": fx.payload("A"), "B": fx.payload("B")}, fail_first={"B": 2})
    limiter = CountingLimiter()
    first = run(writer, feed, universe("A", "B"), limiter, retry_pause_s=7)
    assert first.status is RunStatus.PARTIAL
    assert limiter.held == 7  # the retry pass waited out a shared cool-down first
    second = run(writer, feed, universe("A", "B"), retry_pause_s=0)
    assert second.run_id == first.run_id
    assert second.status is RunStatus.COMPLETE
    assert feed.calls.count("A") == 1  # finished tickers are not fetched again
    assert StoreReader(LocalBackend(tmp_path)).table(OPTIONS, DAY) is not None


def test_mass_no_chain_is_suspicious() -> None:
    writer = StoreWriter(MemoryBackend())
    record = run(writer, FakeFeed({"A": fx.payload("A")}), universe("A", "X", "Y"), retry_pause_s=0)
    assert record.status is RunStatus.PARTIAL
    assert "returned no chain" in record.stats["partial"][0]


def test_features_job_scores_liquidity() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    deep = fx.payload("DEEP", options=fx.chain("DEEP", spread=0.02, oi=5000))
    feed = FakeFeed(
        {"DEEP": deep, "THIN": fx.payload("THIN", options=fx.chain("THIN", spread=1.5, oi=3))}
    )
    run(writer, feed, universe("DEEP", "THIN", "GONE"), retry_pause_s=0)
    record = compute_option_liquidity(task_ctx(writer, reader, CLOCK), DAY)
    assert record.stats["liq_status"] == {"OK": 2, "NO_CHAIN": 1}
    frame = reader.table(TABLE, DAY)
    assert frame is not None
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
    import pytest  # noqa: PLC0415

    from algotrade.core.errors import DataValidationError  # noqa: PLC0415

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
