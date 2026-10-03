"""The ``rates`` task: one partition per curve date, one request per year, resumable."""

from datetime import date

import pytest

from algotrade.data import StoreReader
from algotrade.data.rates import curve
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.sources.framework.http import HttpError, RetryPolicy
from algotrade_ingestion.sources.vendors.treasury.par_yields import TreasuryParYields
from algotrade_ingestion.tasks.framework.registry import run_task
from algotrade_ingestion.tasks.market.rates import TABLE, ingest_rates
from tests.helpers.ingest_fakes import http_for, task_ctx
from tests.helpers.payloads import treasury as treasury_payloads


def _source(urls: list[str], fail_year: int | None = None) -> TreasuryParYields:
    def transport(url: str) -> bytes:
        urls.append(url)
        if fail_year is not None and f"/{fail_year}/" in url:
            raise HttpError(500)
        if "/2025/" in url:
            return treasury_payloads.payload(2025)
        return b""  # a year with nothing published yet

    return TreasuryParYields(http_for(transport, RetryPolicy(tries=1)))


def test_backfill_writes_each_curve_date_once() -> None:
    backend, urls = MemoryBackend(), []
    ctx = task_ctx(StoreWriter(backend))
    record = ingest_rates(ctx, _source(urls), date(2025, 1, 3), date(2026, 1, 5))
    assert record.status is RunStatus.COMPLETE
    assert len(urls) == 2  # one request per year
    assert record.items == {"2025": "OK: 4 curves", "2026": "NO_DATA"}
    reader = StoreReader(backend)
    assert reader.dates(TABLE) == [
        date(2025, 1, 3),
        date(2025, 12, 29),
        date(2025, 12, 30),
        date(2025, 12, 31),
    ]
    assert record.stats["curves"] == 4 and record.stats["latest"] == "2025-12-31"
    stored = reader.table(TABLE, date(2025, 12, 31))
    assert stored is not None and len(stored) == 14
    assert set(stored["source"]) == {"treasury"}
    assert float(curve(reader, date(2026, 1, 2)).rate(30 / 365)) == pytest.approx(0.0374, abs=1e-4)
    again = ingest_rates(ctx, _source(urls), date(2025, 12, 30), date(2025, 12, 31))
    assert again.items == {"2025": "OK: 0 curves"}  # stored dates are skipped
    forced = ingest_rates(ctx, _source(urls), date(2025, 12, 30), date(2025, 12, 31), force=True)
    assert forced.items == {"2025": "OK: 2 curves"}


def test_a_failed_year_makes_the_run_partial() -> None:
    record = ingest_rates(
        task_ctx(StoreWriter(MemoryBackend())),
        _source([], 2026),
        date(2025, 12, 1),
        date(2026, 1, 9),
    )
    assert record.status is RunStatus.PARTIAL
    assert record.items["2026"].startswith("FETCH_ERROR")


def test_empty_window_is_rejected() -> None:
    with pytest.raises(ValueError, match="empty window"):
        ingest_rates(
            task_ctx(StoreWriter(MemoryBackend())), _source([]), date(2025, 2, 1), date(2025, 1, 1)
        )


def test_registry_defaults_to_the_lookback_window() -> None:
    backend, urls = MemoryBackend(), []
    ctx = task_ctx(StoreWriter(backend), sources={"treasury": _source(urls)})
    record = run_task("rates", ctx, {"session": date(2025, 12, 31)})
    assert record.stats["window"] == ["2025-12-22", "2025-12-31"]  # lookback_days (default 10)
    assert StoreReader(backend).dates(TABLE)[0] == date(2025, 12, 29)
