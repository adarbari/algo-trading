"""Tiingo's monthly symbol cap is one count for bars-history and winners-sample."""

from datetime import UTC, date, datetime
from pathlib import Path

from algotrade.config.site.settings import SourcesSettings
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import IngestRun
from algotrade_ingestion.tasks.framework.tiingo_budget import month_symbols
from algotrade_ingestion.tasks.listings.winners_sample import ingest_winners_sample, pick_sample
from algotrade_sources.framework.http import RetryPolicy
from algotrade_sources.vendors.tiingo.prices import TiingoDailyPrices
from tests.apps.ingestion.tasks.listings.test_winners_sample import (
    DAY,
    SMALL,
    Prices,
    listings,
    store,
    ticking,
)
from tests.helpers.ingest_fakes import http_for, task_ctx


def cap(n: int) -> SourcesSettings:
    return SourcesSettings(tiingo_monthly_symbol_budget=n)


def spent(writer: StoreWriter, task: str, prefix: str, n: int) -> None:
    started = datetime(2026, 10, 2, 9, tzinfo=UTC)
    record = RunRecord(f"{task}-spent", task, DAY, started)
    record.status, record.finished_at = RunStatus.COMPLETE, started
    record.items = {f"{prefix}{i}": "OK: w" for i in range(n)}
    writer._backend.runs.save(record)  # type: ignore[attr-defined]


def test_a_bars_history_month_of_400_symbols_makes_the_sample_refuse() -> None:
    writer = StoreWriter(MemoryBackend())
    store(writer, listings())
    spent(writer, "bars_history", "hist:EQ:X", 400)
    prices = Prices(pick_sample(listings(), 1, **SMALL))
    ctx = task_ctx(
        writer, clock=ticking, settings=SourcesSettings(tiingo_monthly_symbol_budget=430)
    )
    source = TiingoDailyPrices(http_for(prices, RetryPolicy(tries=1)))
    record = ingest_winners_sample(ctx, source, DAY, Path("/nonexistent/r.json"), seed=1, **SMALL)
    assert record.status is RunStatus.FAILED and prices.calls == []
    assert "only 30 of the month's 430" in record.stats["failed_because"][0]
    assert (record.stats["month_budget"], record.stats["month_used"]) == (430, 400)


def test_the_sample_s_symbols_count_against_bars_history(tmp_path: Path) -> None:
    writer = StoreWriter(MemoryBackend())
    store(writer, listings())
    picks = pick_sample(listings(), 1, **SMALL)
    ctx = task_ctx(
        writer, clock=ticking, settings=SourcesSettings(tiingo_monthly_symbol_budget=450)
    )
    source = TiingoDailyPrices(http_for(Prices(picks), RetryPolicy(tries=1)))
    done = ingest_winners_sample(ctx, source, DAY, tmp_path / "r.json", seed=1, **SMALL)
    assert done.status is RunStatus.COMPLETE and done.stats["month_used"] == 0
    assert done.stats["month_remaining"] == 450 - len(picks)
    later = task_ctx(writer, clock=lambda: datetime(2026, 10, 9, tzinfo=UTC))
    with IngestRun(later, "bars_history", date(2026, 10, 9)) as run:
        assert len(month_symbols(run)) == len(picks)
        run.record_item("hist:EQ:NEW", "OK: w")
        run.record_item("split:EQ:NEW", "SPLIT_MISMATCH: 1")  # not a symbol
        assert len(month_symbols(run)) == len(picks) + 1
