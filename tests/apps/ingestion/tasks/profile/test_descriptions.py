"""The descriptions task: stocks from Massive (capped, prioritised, refreshed after a long
window, markers for tickers without text) and ETFs from SEC prospectus data (each quarter read
once). Sources are recorded or synthetic payloads behind fake transports."""

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.data.reference import descriptions, stored_descriptions
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.profile.descriptions import (
    FUND_TEXT,
    MASSIVE_TEXT,
    DescriptionSources,
    fund_rows,
    ingest_descriptions,
    recent_quarters,
)
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.massive.overview import MassiveOverview
from algotrade_sources.vendors.sec.fund_objectives import SecFundObjectives, SecFundTickerMap
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for, task_ctx
from tests.helpers.payloads import massive as massive_payloads
from tests.helpers.stored_frames import stamped

DAY = date(2026, 10, 2)
CLOCK = lambda: datetime(2026, 10, 2, 22, tzinfo=UTC)  # noqa: E731
SEC = REPO_ROOT / "tests" / "fixtures" / "sources" / "sec"
ZIP = (SEC / "rr1_2026q2_sample.zip").read_bytes()
FUNDS = (SEC / "company_tickers_mf_sample.json").read_bytes()
TEXT = {"AAPL": "Apple makes phones.", "KO": "Coca-Cola sells drinks.", "ZZZ": "Zed does things."}


class FakeMassive:
    def __init__(self, broken: set[str] | None = None, empty: set[str] | None = None) -> None:
        self.asked: list[str] = []
        self.broken, self.empty = broken or set(), empty or set()

    def __call__(self, url: str) -> bytes:
        ticker = url.rsplit("/", 1)[1]
        self.asked.append(ticker)
        if ticker in self.broken:
            raise HttpError(500)
        if ticker == "GONE":
            raise HttpError(404)
        text = None if ticker in self.empty else TEXT.get(ticker)
        return massive_payloads.overview(ticker, text, f"https://{ticker}.example", 1000)


class FakeSec:
    def __init__(self, published: tuple[str, ...] = ("2026q2",)) -> None:
        self.urls: list[str] = []
        self.published = published

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        if url.endswith(".json"):
            return FUNDS
        if not any(q in url for q in self.published):
            raise HttpError(404)
        return ZIP

    def quarters(self) -> list[str]:
        return [u.rsplit("/", 1)[1].removesuffix("_rr1.zip") for u in self.urls if "zip" in u]


def sources(
    massive: FakeMassive | None, sec: FakeSec | None, per_night: int = 100, refresh_days: int = 365
) -> DescriptionSources:
    policy = RetryPolicy(tries=1)
    return DescriptionSources(
        MassiveOverview(http_for(massive, policy)) if massive else None,
        SecFundTickerMap(http_for(sec, policy)) if sec else None,
        SecFundObjectives(http_for(sec, policy)) if sec else None,
        per_night,
        refresh_days,
        fund_quarters=2,
        priority_symbols=("ZZZ",),
    )


STOCKS = ("AAPL", "KO", "ZZZ", "GONE")
ETFS = ("VOO", "BLV", "FJP", "MNVR", "QQQ", "SPY")


def store() -> tuple[StoreWriter, StoreReader]:
    """Reference on DAY: four stocks (AAPL and KO in the S&P 500, ZZZ pinned), six ETFs
    (SPY is not in the SEC fund map, QQQ has no objective in the recorded quarter), a warrant."""
    writer = StoreWriter(MemoryBackend())
    rows = [
        {"instrument_id": f"EQ:{s}", "symbol": s, "asset_class": "EQ", "multiplier": 1.0,
         "security_type": "COMMON_STOCK", "status": "ACTIVE", "is_etf": False,
         "in_sp500": s in ("AAPL", "KO")}
        for s in STOCKS
    ] + [
        {"instrument_id": f"EQ:{s}", "symbol": s, "asset_class": "EQ", "multiplier": 1.0,
         "security_type": "ETF", "status": "ACTIVE", "is_etf": True, "in_sp500": False}
        for s in ETFS
    ] + [
        {"instrument_id": "EQ:WARR", "symbol": "WARR", "asset_class": "EQ", "multiplier": 1.0,
         "security_type": "WARRANT", "status": "ACTIVE", "is_etf": False, "in_sp500": False}
    ]  # fmt: skip
    writer.write_table("instruments/reference", DAY, "u", stamped(rows, DAY, "u"))
    return writer, StoreReader(writer._backend)


def run(
    writer: StoreWriter,
    reader: StoreReader,
    srcs: DescriptionSources,
    day: date = DAY,
    *,
    only: str | None = None,
    limit: int | None = None,
    symbols: tuple[str, ...] = (),
    force: bool = False,
) -> RunRecord:
    ctx = task_ctx(writer, reader, CLOCK)
    return ingest_descriptions(ctx, srcs, day, only=only, limit=limit, symbols=symbols, force=force)


def test_first_run_describes_stocks_by_priority_and_etfs_from_the_prospectus() -> None:
    writer, reader = store()
    massive, sec = FakeMassive(), FakeSec()
    record = run(writer, reader, sources(massive, sec))
    assert record.status is RunStatus.COMPLETE
    assert massive.asked == ["ZZZ", "AAPL", "KO", "GONE"]  # pinned, S&P 500, the rest
    s = record.stats
    assert (s["stocks"], s["due"], s["requested"], s["deferred_by_cap"]) == (4, 4, 4, 0)
    assert s["fund_quarters"] == ["2026q2", "2026q3"] == s["fund_quarters_todo"]
    assert sec.quarters() == ["2026q2", "2026q3"]  # 2026q3 is not published in the fake: 404
    got = descriptions(reader).set_index("symbol")
    assert set(got.index) == {"AAPL", "KO", "ZZZ", "VOO", "BLV", "FJP", "MNVR"}
    assert got.loc["AAPL", "description"] == "Apple makes phones."
    assert got.loc["AAPL", "description_source"] == MASSIVE_TEXT
    assert got.loc["AAPL", "homepage_url"] == "https://AAPL.example"
    assert got.loc["AAPL", "total_employees"] == 1000
    assert got.loc["VOO", "description_source"] == FUND_TEXT
    assert got.loc["VOO", "description"].startswith("Vanguard 500 Index Fund (the Fund) seeks")
    assert got.loc["BLV", "description"] == got.loc["BLV", "description"].strip()
    assert isinstance(got.loc["VOO", "filed"], date) and got.loc["VOO", "accn"]
    assert "QQQ" not in got.index and "SPY" not in got.index and "WARR" not in got.index
    markers = stored_descriptions(reader).set_index("symbol")
    assert pd.isna(markers.loc["GONE", "description"])  # Massive does not know it: a marker
    assert markers.loc["GONE", "fetched_on"] == DAY
    assert "WARR" not in markers.index and "SPY" not in markers.index
    raw = writer.raw.get("massive", "ticker_overview", DAY, record.run_id, "AAPL")
    assert raw is not None and b"Apple makes phones." in raw
    assert writer.raw.get("sec_edgar", "fund_objectives", DAY, record.run_id, "2026q2") == ZIP


def test_the_cap_defers_and_a_second_run_continues_without_rereading_quarters() -> None:
    writer, reader = store()
    first = FakeMassive()
    record = run(writer, reader, sources(first, FakeSec(("2026q2", "2026q3")), per_night=2))
    assert first.asked == ["ZZZ", "AAPL"]
    assert (record.stats["requested"], record.stats["deferred_by_cap"]) == (2, 2)
    assert len(descriptions(reader)) == 2 + 4  # two stocks and four ETFs
    again, sec = FakeMassive(), FakeSec(("2026q2", "2026q3"))
    record = run(writer, reader, sources(again, sec, per_night=2), DAY + timedelta(days=1))
    assert again.asked == ["KO", "GONE"]  # the next in order; the first two are not asked again
    assert sec.urls == []  # both quarters were read by the first run
    assert record.stats["fund_quarters_todo"] == []
    last = FakeMassive()
    record = run(writer, reader, sources(last, FakeSec()), DAY + timedelta(days=2))
    assert last.asked == [] and record.stats["requested"] == 0


def test_a_quarter_not_published_yet_is_tried_again_and_is_not_a_failure() -> None:
    writer, reader = store()
    sec = FakeSec(published=())
    record = run(writer, reader, sources(None, sec), only="funds")
    assert record.status is RunStatus.COMPLETE
    assert record.items["fund:2026q2"] == "NOT_PUBLISHED" and descriptions(reader).empty
    later = FakeSec(published=("2026q2",))
    record = run(writer, reader, sources(None, later), DAY + timedelta(days=1), only="funds")
    assert record.stats["fund_quarters_todo"] == ["2026q2", "2026q3"]
    assert len(descriptions(reader)) == 4
    assert record.stats["fund_rows"] == 4


def test_a_refresh_after_the_window_keeps_text_the_vendor_no_longer_has() -> None:
    writer, reader = store()
    run(writer, reader, sources(FakeMassive(), None), only="massive")
    soon = FakeMassive()
    run(writer, reader, sources(soon, None, refresh_days=365), DAY, only="massive")
    assert soon.asked == []  # just described: not due for a year
    later = FakeMassive(empty={"AAPL"})
    record = run(writer, reader, sources(later, None, refresh_days=365), DAY + timedelta(days=400))
    assert set(later.asked) == {"ZZZ", "AAPL", "KO", "GONE"}  # every slot passed in 400 days
    assert record.items["AAPL"] == "KEPT"
    got = descriptions(reader).set_index("symbol")
    assert got.loc["AAPL", "description"] == "Apple makes phones."
    assert got.loc["AAPL", "fetched_on"] == DAY + timedelta(days=400)


def test_errors_make_the_run_partial_and_the_ticker_is_asked_again() -> None:
    writer, reader = store()
    record = run(writer, reader, sources(FakeMassive(broken={"KO"}), None), only="massive")
    assert record.status is RunStatus.PARTIAL and record.stats["failed_count"] == 1
    assert record.stats["failed"][0].startswith("KO")
    assert "KO" not in set(stored_descriptions(reader)["symbol"])
    retry = FakeMassive()
    run(writer, reader, sources(retry, None), DAY + timedelta(days=1), only="massive")
    assert retry.asked == ["KO"]


def test_symbols_narrow_the_stocks_and_skip_the_etfs() -> None:
    writer, reader = store()
    massive, sec = FakeMassive(), FakeSec()
    record = run(writer, reader, sources(massive, sec), symbols=("ko",))
    assert massive.asked == ["KO"] and sec.urls == []
    assert record.stats["stocks"] == 1
    forced = FakeMassive()
    run(writer, reader, sources(forced, sec), symbols=("KO",), force=True)
    assert forced.asked == ["KO"]  # force asks again


def test_force_rereads_quarters_and_unavailable_sources_are_reported() -> None:
    writer, reader = store()
    sec = FakeSec(("2026q2", "2026q3"))
    run(writer, reader, sources(None, sec), only="funds")
    sec.urls.clear()
    run(writer, reader, sources(None, sec), DAY + timedelta(days=1), only="funds")
    assert sec.urls == []
    record = run(
        writer, reader, sources(None, sec), DAY + timedelta(days=2), only="funds", force=True
    )
    assert sec.quarters() == ["2026q2", "2026q3"]
    assert record.stats["fund_rows"] == 0  # same filings, same text: nothing to store
    off = run(writer, reader, sources(None, None), DAY + timedelta(days=3))
    assert "skipped" in off.stats["massive"] and "skipped" in off.stats["funds"]
    assert off.status is RunStatus.COMPLETE


def test_a_bad_only_value_is_refused() -> None:
    writer, reader = store()
    with pytest.raises(ValueError, match="only"):
        run(writer, reader, sources(None, None), only="everything")


def test_recent_quarters_are_the_completed_ones_oldest_first() -> None:
    assert recent_quarters(date(2026, 10, 4), 3) == ["2026q1", "2026q2", "2026q3"]
    assert recent_quarters(date(2026, 1, 15), 2) == ["2025q3", "2025q4"]
    assert recent_quarters(date(2026, 4, 1), 5) == [
        "2025q1", "2025q2", "2025q3", "2025q4", "2026q1",
    ]  # fmt: skip
    assert recent_quarters(DAY, 0) == []


def test_a_later_filing_replaces_an_objective_but_an_older_one_does_not() -> None:
    etfs = pd.DataFrame({"instrument_id": ["EQ:VOO"], "symbol": ["VOO"]})
    funds = pd.DataFrame({"symbol": ["VOO"], "series_id": ["S1"]})

    def objective(text: str, filed: date | None) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "series_id": ["S1"],
                "objective": [text],
                "accn": ["a"],
                "form": ["x"],
                "filed": [filed],
            }
        ).astype(object)

    stored = pd.DataFrame(
        [{"instrument_id": "EQ:VOO", "description_source": FUND_TEXT,
          "description": "Old objective for the Fund.", "filed": date(2026, 4, 1)}]
    )  # fmt: skip
    newer = fund_rows(
        [objective("New objective for the Fund.", date(2026, 7, 1))], funds, etfs, stored
    )
    assert list(newer["description"]) == ["New objective for the Fund."]
    older = fund_rows(
        [objective("Older objective for the Fund.", date(2026, 1, 1))], funds, etfs, stored
    )
    assert older.empty
    same = fund_rows(
        [objective("Old objective for the Fund.", date(2026, 7, 1))], funds, etfs, stored
    )
    assert same.empty  # a new filing with the same words changes nothing
    unknown = fund_rows([objective("Undated objective for the Fund.", None)], funds, etfs, stored)
    assert unknown.empty  # undated text never replaces a dated one
    forced = fund_rows(
        [objective("Older objective for the Fund.", date(2026, 1, 1))], funds, etfs, stored, True
    )
    assert list(forced["description"]) == ["Older objective for the Fund."]  # a forced reread
    assert fund_rows([], funds, etfs, stored).empty
