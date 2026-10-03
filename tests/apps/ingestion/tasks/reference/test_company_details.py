"""The company-details job: CIK joins, incremental refresh, failures and the L1 view."""

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from algotrade.core.errors import MissingDataError
from algotrade.data import StoreReader
from algotrade.data.reference import instrument_view
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.sources.framework.http import HttpError, RetryPolicy
from algotrade_ingestion.sources.vendors.sec.edgar import TICKERS_URL, SecSubmissions, SecTickerMap
from algotrade_ingestion.tasks.reference.company_details import (
    TABLE,
    CompanySources,
    due_ciks,
    ingest_company_details,
)
from tests.ingest_helpers import http_for, task_ctx
from tests.sec_fixture import submissions, tickers
from tests.storage_helpers import stamped

DAY = date(2026, 10, 2)
CLOCK = lambda: datetime(2026, 10, 2, 22, tzinfo=UTC)  # noqa: E731
COMPANIES = {
    320193: submissions(320193, "Apple Inc."),
    789019: submissions(789019, "MICROSOFT CORP", "7372", "Services-Prepackaged Software"),
}


class FakeSec:
    """Serves the ticker map and submissions; records every URL requested."""

    def __init__(self, broken: set[str] | None = None) -> None:
        self.urls: list[str] = []
        self.broken = broken or set()

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        if url in self.broken:
            raise HttpError(500)
        if url == TICKERS_URL:
            return tickers(
                [
                    (320193, "Apple Inc.", "AAPL", "Nasdaq"),
                    (789019, "MICROSOFT CORP", "MSFT", "Nasdaq"),
                    (884394, "SPDR S&P 500 ETF TRUST", "SPY", "NYSE"),
                ]
            )
        cik = int(url.rsplit("CIK", 1)[1].removesuffix(".json"))
        if cik not in COMPANIES:
            raise HttpError(404)
        return COMPANIES[cik]

    @property
    def submissions_requested(self) -> int:
        return sum("submissions" in u for u in self.urls)


def sources(feed: FakeSec, refresh_days: int = 30) -> CompanySources:
    policy = RetryPolicy(tries=1)
    return CompanySources(
        SecTickerMap(http_for(feed, policy)),
        SecSubmissions(http_for(feed, policy)),
        refresh_days,
    )


def store(day: date = DAY) -> tuple[StoreWriter, StoreReader]:
    """A reference snapshot on ``day`` with four instruments."""
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    rows = [
        # AAPL: CIK from Massive (reference); MSFT, SPY: from the SEC map; WEIRD: no CIK at all
        ("AAPL", "COMMON_STOCK", "0000320193"),
        ("MSFT", "COMMON_STOCK", None),
        ("SPY", "ETF", None),
        ("WEIRD", "ETF", None),
    ]
    reference = [
        {
            "instrument_id": f"EQ:{s}",
            "symbol": s,
            "asset_class": "equity",
            "security_type": t,
            "multiplier": 1.0,
            "status": "ACTIVE",
            "cik": cik,
        }
        for s, t, cik in rows
    ]
    writer.write_table("instruments/reference", day, "u", stamped(reference, day, "u"))
    return writer, StoreReader(backend)


def test_first_run_fetches_every_cik_and_counts_funds() -> None:
    writer, reader = store()
    feed = FakeSec()
    record = ingest_company_details(task_ctx(writer, reader, CLOCK), sources(feed), DAY)
    assert record.status is RunStatus.COMPLETE
    s = record.stats
    assert (s["cik_from_reference"], s["cik_from_sec_map"], s["no_cik"]) == (1, 2, 1)
    assert (s["ciks"], s["requested"], s["fetched"], s["no_submissions"], s["rows"]) == (
        3,
        3,
        2,
        1,
        2,
    )
    company = reader.table(TABLE, DAY)
    assert company is not None
    rows = company.set_index("instrument_id")
    assert rows.loc["EQ:AAPL", "sector"] == "Technology"
    assert rows.loc["EQ:MSFT", "cik_source"] == "sec_map"
    assert rows.loc["EQ:MSFT", "industry"] == "Services-Prepackaged Software"
    assert set(company["source"]) == {"sec_edgar"}
    raw = writer.raw.get("sec_edgar", "submissions", DAY, record.run_id, "0000320193")
    assert raw == COMPANIES[320193]
    assert writer.raw.get("sec_edgar", "company_tickers", DAY, record.run_id, "tickers")


def test_nightly_runs_are_incremental() -> None:
    writer, reader = store()
    first = FakeSec()
    ingest_company_details(task_ctx(writer, reader, CLOCK), sources(first, refresh_days=30), DAY)
    nxt = DAY + timedelta(days=1)
    again = FakeSec()
    record = ingest_company_details(task_ctx(writer, reader, CLOCK), sources(again), nxt)
    # Fresh companies are carried forward; only the CIK with no submissions is retried.
    assert (record.stats["requested"], again.submissions_requested) == (1, 1)
    company = reader.table(TABLE, nxt)
    assert company is not None and len(company) == 2
    later = DAY + timedelta(days=31)
    stale = FakeSec()
    record = ingest_company_details(task_ctx(writer, reader, CLOCK), sources(stale), later)
    assert record.stats["requested"] == 3  # both stored companies are past refresh_days
    forced = FakeSec()
    record = ingest_company_details(
        task_ctx(writer, reader, CLOCK), sources(forced), nxt, force=True
    )
    assert forced.submissions_requested == 3


def test_limit_defers_and_errors_make_the_run_partial() -> None:
    writer, reader = store()
    feed = FakeSec(broken={"https://data.sec.gov/submissions/CIK0000789019.json"})
    record = ingest_company_details(task_ctx(writer, reader, CLOCK), sources(feed), DAY, limit=2)
    assert record.status is RunStatus.PARTIAL
    assert (record.stats["requested"], record.stats["deferred_by_limit"]) == (2, 1)
    assert record.stats["failed"][0].startswith("0000789019")
    assert record.stats["rows"] == 1  # AAPL


def test_ticker_map_failure_still_uses_reference_ciks() -> None:
    writer, reader = store()
    record = ingest_company_details(
        task_ctx(writer, reader, CLOCK), sources(FakeSec(broken={TICKERS_URL})), DAY
    )
    assert record.status is RunStatus.PARTIAL
    assert (record.stats["cik_from_sec_map"], record.stats["rows"]) == (0, 1)


def test_nothing_known_writes_nothing() -> None:
    writer, reader = store()
    backup = dict(COMPANIES)
    COMPANIES.clear()
    try:
        record = ingest_company_details(task_ctx(writer, reader, CLOCK), sources(FakeSec()), DAY)
    finally:
        COMPANIES.update(backup)
    assert (record.stats["rows"], record.stats["no_submissions"]) == (0, 3)
    assert reader.table(TABLE, DAY) is None


def test_needs_a_reference_snapshot() -> None:
    backend = MemoryBackend()
    with pytest.raises(MissingDataError):
        ingest_company_details(
            task_ctx(StoreWriter(backend), StoreReader(backend), CLOCK), sources(FakeSec()), DAY
        )


def test_due_ciks_orders_new_then_stalest() -> None:
    previous = pd.DataFrame(
        {"cik": ["2", "3", "4"], "fetched_on": [date(2026, 1, 1), date(2025, 1, 1), DAY]}
    )
    assert due_ciks(["1", "2", "3", "4"], previous, DAY, 30, False) == ["1", "3", "2"]
    assert due_ciks(["2", "1"], previous, DAY, 30, True) == ["1", "2"]
    assert due_ciks(["2", "1"], None, DAY, 30, False) == ["1", "2"]


def test_instrument_view_exposes_company_fields() -> None:
    writer, reader = store()
    nxt = DAY + timedelta(days=1)
    ingest_company_details(task_ctx(writer, reader, CLOCK), sources(FakeSec()), nxt)
    view = instrument_view(
        reader, nxt + timedelta(days=3), ["instrument.symbol", "instrument.sector"]
    )
    assert view.missing == ()
    sectors = view.frame.set_index("instrument_id")["instrument.sector"]
    assert sectors["EQ:AAPL"] == "Technology"
    assert pd.isna(sectors["EQ:SPY"])  # no submissions: UNKNOWN to selections
    before = instrument_view(reader, DAY, ["instrument.sector"])
    assert before.missing == ()  # before the first company snapshot: the earliest (one rule)
    assert before.frame.set_index("instrument_id")["instrument.sector"]["EQ:AAPL"] == "Technology"
