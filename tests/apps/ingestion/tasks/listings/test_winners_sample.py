"""The winners-sample task on the recorded supported-tickers slice: the seeded strata, the
200-symbol cap, the coverage report and the resume. Prices are generated for the exchange
sessions of each listing (Tiingo's price payload shape), never fetched."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from algotrade.core.time.calendar import sessions_between
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.listings.sample_coverage import DELISTED, LIVE, WINNER, Pick
from algotrade_ingestion.tasks.listings.winners_sample import (
    BIG_WINNERS,
    MAX_SYMBOLS,
    SINCE,
    ingest_winners_sample,
    pick_sample,
)
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.tiingo.listings import parse_listings
from algotrade_sources.vendors.tiingo.prices import TiingoDailyPrices
from tests.helpers.ingest_fakes import http_for, task_ctx
from tests.helpers.payloads import tiingo as payloads

DAY = date(2026, 10, 8)
CLOCK = lambda: datetime(2026, 10, 8, 22, tzinfo=UTC)  # noqa: E731
SMALL = {"per_year": 2, "live": 6, "winners": 6}


_NOW = [CLOCK()]


def ticking() -> datetime:
    """A clock that moves 7 s on every call, across runs: each run of a session gets its own id."""
    _NOW[0] += timedelta(seconds=7)
    return _NOW[0]


def listings() -> pd.DataFrame:
    return parse_listings(payloads.supported_tickers_zip())[0]


def store(writer: StoreWriter, frame: pd.DataFrame) -> None:
    rows = frame.assign(
        instrument_id=None,
        ts=pd.Timestamp(DAY, tz="UTC"),
        session_date=DAY,
        knowledge_ts=pd.Timestamp(CLOCK()),
        source="tiingo",
        run_id="l",
    )
    writer.write_table("instruments/listing_history", DAY, "l", rows.astype(object))


def test_the_sample_has_the_strata_is_seeded_and_never_asks_for_a_symbol_twice() -> None:
    frame = listings()
    picks = pick_sample(frame, 1, **SMALL)
    assert picks == pick_sample(frame, 1, **SMALL)  # reproducible
    assert picks != pick_sample(frame, 2, **SMALL)  # the seed matters
    by = {s: [p for p in picks if p.stratum == s] for s in (DELISTED, LIVE, WINNER)}
    assert (len(by[WINNER]), len(by[LIVE]), len(by[DELISTED])) == (6, 6, 20)
    assert len({p.ticker for p in picks}) == len(picks)
    assert all(p.ticker in BIG_WINNERS and p.end_date is None for p in by[WINNER])
    assert all(p.start_date <= date(2010, 12, 31) and p.end_date is None for p in by[LIVE])
    years = sorted(p.end_date.year for p in by[DELISTED])
    assert years == [y for y in range(2011, 2021) for _ in range(2)]


def test_only_stocks_of_the_four_exchanges_listed_a_year_are_sampled() -> None:
    frame = listings()
    stocks = frame[frame["asset_type"] == "Stock"].set_index(["ticker", "start_date"])
    for p in pick_sample(frame, 3, **SMALL):
        row = stocks.loc[(p.ticker, p.start_date)]
        assert row["exchange"] in ("NYSE", "NASDAQ", "AMEX", "ARCA")
        if p.end_date is not None:
            assert (p.end_date - p.start_date).days >= 365


def test_a_recycled_ticker_is_marked_and_the_default_sample_stays_within_the_cap() -> None:
    frame = listings()
    picks = pick_sample(frame, 4)
    assert len({p.ticker for p in picks}) <= MAX_SYMBOLS
    counts = frame["ticker"].value_counts()
    assert all(p.recycled == (counts[p.ticker] > 1) for p in picks)
    assert any(p.recycled for p in pick_sample(frame, 4, 12, 0, 0))  # AAC-like names exist


def test_a_sample_over_the_cap_is_refused() -> None:
    import pytest  # noqa: PLC0415

    with pytest.raises(ValueError, match="more than 200"):
        pick_sample(listings(), 1, per_year=10, live=60, winners=50)


class Prices:
    """A fake Tiingo: the sessions of each sampled listing (and, for a recycled ticker, of the
    other company's earlier listing as well), 4 sessions missing in the middle of one name."""

    def __init__(self, picks: list[Pick], leak: str | None = None) -> None:
        self.windows = {p.ticker: p for p in picks}
        self.calls: list[str] = []
        self.leak = leak

    def __call__(self, url: str) -> bytes:
        ticker = url.split("/daily/")[1].split("/", maxsplit=1)[0]
        self.calls.append(ticker)
        pick = self.windows[ticker]
        last = pick.end_date or DAY
        days = sessions_between(max(pick.start_date, SINCE), last)
        if ticker == "GAPPY":
            days = days[:100] + days[104:]
        if ticker == self.leak:
            days = sessions_between(date(2010, 1, 4), date(2010, 1, 8)) + days
        rows = [(d.isoformat(), 10.0, 11.0, 9.0, 10.5, 1000.0) for d in days]
        return payloads.prices(rows)


def run(writer: StoreWriter, prices: Prices, report: Path, **kw: object):
    source = TiingoDailyPrices(http_for(prices, RetryPolicy(tries=1)))
    ctx = task_ctx(writer, clock=ticking)
    return ctx, ingest_winners_sample(ctx, source, DAY, report, seed=1, **SMALL, **kw)  # type: ignore[arg-type]


def test_task_fetches_each_name_once_grades_it_and_writes_the_report_not_a_table(
    tmp_path: Path,
) -> None:
    writer = StoreWriter(MemoryBackend())
    store(writer, listings())
    picks = pick_sample(listings(), 1, **SMALL)
    prices = Prices(picks)
    ctx, record = run(writer, prices, tmp_path / "report.json")
    assert record.status is RunStatus.COMPLETE and sorted(prices.calls) == sorted(
        p.ticker for p in picks
    )
    assert ctx.reader.dates("bars/1d") == []  # nothing enters a table
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["listing_snapshot"] == DAY.isoformat() and len(report["names"]) == len(picks)
    summary = report["summary"]
    assert summary["pass_delisted_to_end"] and summary["pass_gap_share"]
    assert summary["pass_recycled_clipped"] and summary["no_bars"] == 0
    names = {n["ticker"]: n for n in report["names"]}
    delisted = next(p for p in picks if p.stratum == DELISTED)
    row = names[delisted.ticker]
    assert row["last_bar"] <= delisted.end_date.isoformat() and row["to_end"] is True
    assert row["gap_days"] == 0 and row["bars"] == row["expected_sessions"]
    assert record.stats["symbols"] == len(picks) and record.stats["report"].endswith("report.json")
    winner = next(n for n in names.values() if n["stratum"] == WINNER)
    assert winner["ratio_2010_2016"] == 1.0  # flat generated prices, no split


def test_a_second_run_does_not_ask_again_for_what_the_first_fetched(tmp_path: Path) -> None:
    writer = StoreWriter(MemoryBackend())
    store(writer, listings())
    picks = pick_sample(listings(), 1, **SMALL)
    prices = Prices(picks)
    _, first = run(writer, prices, tmp_path / "r.json", limit=5)
    assert first.status is RunStatus.PARTIAL and first.stats["fetched"] == 5
    assert first.stats["pending"] == len(picks) - 5
    _, second = run(writer, prices, tmp_path / "r.json")
    assert second.status is RunStatus.COMPLETE and len(prices.calls) == len(picks)
    assert len(set(prices.calls)) == len(picks)  # never a symbol twice
    assert len(json.loads((tmp_path / "r.json").read_text())["names"]) == len(picks)  # merged


def test_without_a_listing_snapshot_the_run_fails_and_says_what_to_run_first(
    tmp_path: Path,
) -> None:
    writer = StoreWriter(MemoryBackend())
    _, record = run(writer, Prices([]), tmp_path / "r.json")
    assert record.status is RunStatus.FAILED
    assert "listing-history" in str(record.stats["failed_because"])
    assert not (tmp_path / "r.json").exists()


def test_a_ticker_tiingo_does_not_know_is_no_data_and_a_dead_key_stops_the_run(
    tmp_path: Path,
) -> None:
    writer = StoreWriter(MemoryBackend())
    store(writer, listings())

    def unknown(url: str) -> bytes:
        raise HttpError(404)

    source = TiingoDailyPrices(http_for(unknown, RetryPolicy(tries=1)))
    ctx = task_ctx(writer, clock=CLOCK)
    record = ingest_winners_sample(ctx, source, DAY, tmp_path / "a.json", seed=1, **SMALL)
    assert record.stats["summary"]["no_bars"] == len(record.items)
    assert not record.stats["summary"]["pass_delisted_to_end"]

    def dead(url: str) -> bytes:
        raise HttpError(401)

    source = TiingoDailyPrices(http_for(dead, RetryPolicy(tries=1)))
    other = StoreWriter(MemoryBackend())
    store(other, listings())
    stopped = ingest_winners_sample(
        task_ctx(other, clock=CLOCK), source, DAY, tmp_path / "b.json", seed=1, **SMALL
    )
    assert stopped.status is RunStatus.PARTIAL and len(stopped.items) == 3
