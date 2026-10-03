import json
from datetime import UTC, date, datetime

import pytest

from algotrade.config.env import credential, load_dotenv
from algotrade.core.calendar import sessions_between
from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.sources.base import FetchRequest
from algotrade_ingestion.sources.http import HttpError, RetryPolicy
from algotrade_ingestion.sources.massive import (
    MassiveCorporateActions,
    MassiveDailyBars,
    act_symbol,
    parse_grouped,
)
from algotrade_ingestion.tasks.bars import ingest_daily_bars
from algotrade_ingestion.tasks.corporate_actions import ingest_corporate_actions
from tests import massive_fixture as fx
from tests.ingest_helpers import http_for, task_ctx
from tests.storage_helpers import write_reference

D1, D2 = date(2026, 9, 30), date(2026, 10, 1)
CLOCK = lambda: datetime(2026, 10, 2, 22, tzinfo=UTC)  # noqa: E731
NO_RETRY = RetryPolicy(tries=1)


def test_parse_grouped_maps_tickers_and_drops_bad_rows() -> None:
    bars, invalid = parse_grouped(
        D1,
        fx.grouped(
            D1,
            [
                ("AAPL", 10, 11, 9, 10.5, 1000),
                ("KIMpL", 25, 26, 24, 25.5, 10),
                ("BAD", 10, 9, 8, 10, 5),
                ("ZERO", 0, 1, 0, 1, 5),
            ],
        ),
    )
    assert list(bars["symbol"]) == ["AAPL", "KIM$L"]  # ids are resolved by the job
    assert invalid == 2
    assert str(bars["ts"].dt.tz) == "UTC"
    assert parse_grouped(D1, fx.grouped(D1, []))[0].empty  # holiday
    assert (act_symbol("BRK.B"), act_symbol("KIMpL")) == ("BRK.B", "KIM$L")


def test_corporate_actions_follow_pagination() -> None:
    pages = {
        "first": fx.page(
            [{"ticker": "NVDA", "execution_date": "2026-09-30", "split_from": 1, "split_to": 10}],
            next_url="https://api.massive.com/next",
        ),
        "next": fx.page(
            [{"ticker": "KIMpL", "execution_date": "2026-09-29", "split_from": 2, "split_to": 1}]
        ),
    }
    urls: list[str] = []

    def transport(url: str) -> bytes:
        urls.append(url)
        return pages["next" if url.endswith("/next") else "first"]

    source = MassiveCorporateActions(http_for(transport, NO_RETRY))
    request = FetchRequest("splits:2026-09-01:2026-10-31")
    normalized = source.normalize(request, source.fetch(request) or b"")
    assert normalized is not None
    splits = normalized.tables["events/split"].set_index("symbol")
    assert splits.loc["NVDA", "ratio"] == 10.0
    assert splits.loc["KIM$L", "ratio"] == 0.5
    assert "execution_date.gte=2026-09-01" in urls[0] and len(urls) == 2
    assert "apiKey" not in "".join(urls)  # the key travels in a header, never in URLs


def test_dividends_on_the_same_ex_date_are_summed() -> None:
    payload = fx.page(
        [
            {
                "ticker": "COST",
                "ex_dividend_date": "2026-09-30",
                "cash_amount": 1.3,
                "currency": "USD",
            },
            {
                "ticker": "COST",
                "ex_dividend_date": "2026-09-30",
                "cash_amount": 15.0,
                "currency": "USD",
            },
            {"ticker": "", "ex_dividend_date": "2026-09-30", "cash_amount": 1.0},
        ]
    )
    source = MassiveCorporateActions(http_for(lambda url: payload, NO_RETRY))
    request = FetchRequest("dividends:2026-09-01:2026-10-31")
    normalized = source.normalize(request, source.fetch(request) or b"")
    assert normalized is not None
    dividends = normalized.tables["events/dividend"]
    assert list(dividends["cash_amount"]) == [16.3]


def test_daily_bars_job_resumes_and_records_holidays() -> None:
    calls: list[str] = []

    def transport(url: str) -> bytes:
        calls.append(url)
        if "2026-10-01" in url:
            return fx.grouped(D2, [])  # a holiday
        if "2026-10-02" in url:
            raise HttpError(500)
        return fx.grouped(D1, [("AAPL", 10, 11, 9, 10.5, 1000)])

    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    source = MassiveDailyBars(http_for(transport, NO_RETRY))
    first = ingest_daily_bars(
        task_ctx(writer, reader, CLOCK), source, sessions_between(D1, date(2026, 10, 2))
    )
    assert first.items == {
        "2026-09-30": "OK: 1 bars, 1 unresolved",  # no reference yet: symbol id
        "2026-10-01": "NO_SESSION",
        "2026-10-02": first.items["2026-10-02"],
    }
    assert first.items["2026-10-02"].startswith("FETCH_ERROR")
    assert first.status is RunStatus.PARTIAL
    assert reader.dates("bars/1d") == [D1]
    calls.clear()
    second = ingest_daily_bars(task_ctx(writer, reader, CLOCK), source, [D1])
    assert second.items == {"2026-09-30": "STORED"} and calls == []  # resumed: nothing re-fetched
    forced = ingest_daily_bars(task_ctx(writer, reader, CLOCK), source, [D1], force=True)
    assert forced.items["2026-09-30"].startswith("OK") and len(calls) == 1


def test_corporate_actions_job_writes_snapshots_and_reports_failures() -> None:
    def transport(url: str) -> bytes:
        if "dividends" in url:
            raise HttpError(500)
        return fx.page(
            [{"ticker": "NVDA", "execution_date": "2026-09-30", "split_from": 1, "split_to": 10}]
        )

    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    write_reference(writer, D1, {"NVDA": "EQ:BBG000BBJQV0"})
    source = MassiveCorporateActions(http_for(transport, NO_RETRY))
    record = ingest_corporate_actions(task_ctx(writer, reader, CLOCK), source, D2, D1, D2)
    assert record.status is RunStatus.PARTIAL
    assert (record.stats["events/split"], record.stats["unresolved"]) == (1, 0)
    splits = reader.table("events/split", D2)
    assert splits is not None and list(splits["instrument_id"]) == ["EQ:BBG000BBJQV0"]


def test_daily_bars_resolve_through_the_reference_as_of_each_session() -> None:
    rows = [("META", 10, 11, 9, 10.5, 1000), ("FB", 10, 11, 9, 10.5, 1000)]
    source = MassiveDailyBars(http_for(lambda url: fx.grouped(D1, rows), NO_RETRY))
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    write_reference(writer, D2, {"META": "EQ:BBG000MM2P62"})  # first snapshot after D1
    record = ingest_daily_bars(task_ctx(writer, reader, CLOCK), source, [D1])
    assert record.items["2026-09-30"] == "OK: 2 bars, 1 unresolved"
    bars = reader.table("bars/1d", D1)
    assert bars is not None and list(bars["instrument_id"]) == ["EQ:BBG000MM2P62", "EQ:FB"]
    assert "symbol" not in bars.columns  # the bar schema is unchanged


def test_env_loading_and_missing_key(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"  # type: ignore[operator]
    env.write_text("# comment\nALGOTRADE_MASSIVE_API_KEY='abc'\nOTHER=1\nnot a pair\n")
    monkeypatch.delenv("ALGOTRADE_MASSIVE_API_KEY", raising=False)
    monkeypatch.delenv("OTHER", raising=False)
    load_dotenv(env)
    assert credential("ALGOTRADE_MASSIVE_API_KEY") == "abc"
    monkeypatch.setenv("ALGOTRADE_MASSIVE_API_KEY", "")
    load_dotenv(env)  # never overrides what is already set
    assert credential("ALGOTRADE_MASSIVE_API_KEY") is None  # empty counts as missing
    load_dotenv(tmp_path / "missing")  # type: ignore[operator]
    assert json.loads('{"ok": true}')["ok"]
