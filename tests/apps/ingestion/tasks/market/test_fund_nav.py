"""``fund-nav``: closed-end fund NAVs from Tiingo's MFQS series into ``events/fund_nav``."""

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from itertools import count
from pathlib import Path

import pandas as pd
import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.data import StoreReader
from algotrade.data.events import read_events
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.tiingo_budget import TASKS
from algotrade_ingestion.tasks.market.fund_nav import (
    LOOKBACK_DAYS,
    TASK,
    Fund,
    ingest_fund_nav,
    is_closed_end,
    map_funds,
    nav_rows,
    nav_symbol,
)
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.tiingo.nav import TiingoFundNav, TiingoNavTickers, parse_nav_tickers
from tests.helpers.ingest_fakes import FIXED, http_for, task_ctx
from tests.helpers.payloads import tiingo as payloads
from tests.helpers.stored_frames import stamped

UNTIL = date(2026, 10, 8)  # a Thursday: the day of the recorded listing file
TABLE = "events/fund_nav"
FUNDS = [  # symbol, id, security_type, name
    ("PHK", "EQ:PHK", "CEF", "Pimco High Income Fund"),
    ("GDL", "EQ:GDL", "CEF", "GDL Fund, The Common Shares of Beneficial Interest"),
    ("JPS", "EQ:JPS", "CEF", "Nuveen Preferred & Income Securities Fund"),  # series ended 2024
    ("ADX", "EQ:ADX", "CEF", "Adams Diversified Equity Fund Inc."),  # no MFQS series
    ("CHY", "EQ:CHY", "COMMON_STOCK", "Calamos Convertible and High Income Fund - Closed End Fund"),
    ("CAT", "EQ:CAT", "COMMON_STOCK", "Caterpillar, Inc. Common Stock"),  # XCATX is a real fund
    ("SPY", "EQ:SPY", "ETF", "State Street SPDR S&P 500 ETF Trust"),
]
NAV_DAYS = ["2026-09-30", "2026-10-05", "2026-10-06", "2026-10-07"]
TICKS = count()


class Vendor:
    """Answers the supported-tickers file and a NAV series by symbol (a symbol not in the map is
    a 404, one in ``broken`` a server error); counts the symbols asked."""

    def __init__(self, series: Mapping[str, bytes], broken: tuple[str, ...] = ()):
        self.series, self.broken, self.asked, self.urls = dict(series), broken, [], []

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        if url.endswith("supported_tickers.zip"):
            return payloads.nav_tickers_zip()
        symbol = url.split("/daily/")[1].split("/", maxsplit=1)[0]
        self.asked.append(symbol)
        if symbol in self.broken:
            raise HttpError(500)
        if symbol not in self.series:
            raise HttpError(404)
        return self.series[symbol]


def series(base: float, days: list[str] = NAV_DAYS) -> bytes:
    return payloads.nav_prices([(d, base + i) for i, d in enumerate(days)])


def ticking() -> datetime:
    return FIXED + timedelta(minutes=next(TICKS))


@pytest.fixture(params=["memory", "local"])
def writer(request: pytest.FixtureRequest, tmp_path: Path) -> StoreWriter:
    backend = MemoryBackend() if request.param == "memory" else LocalBackend(tmp_path / "data")
    writer = StoreWriter(backend)
    rows = [
        {"instrument_id": i, "symbol": s, "security_type": t, "name": n, "status": "ACTIVE",
         "asset_class": "EQ", "multiplier": 1.0}
        for s, i, t, n in FUNDS
    ]  # fmt: skip
    day = date(2026, 10, 1)
    writer.write_table("instruments/reference", day, "ref", stamped(rows, day, "ref"))
    return writer


def run(
    writer: StoreWriter,
    vendor: Vendor,
    since: date | None = None,
    until: date = UNTIL,
    budget: int = 450,
    clock=ticking,  # type: ignore[no-untyped-def]
    **kwargs: object,
) -> RunRecord:
    http = http_for(vendor, RetryPolicy(tries=1))
    ctx = task_ctx(
        writer, clock=clock, settings=SourcesSettings(tiingo_monthly_symbol_budget=budget)
    )
    return ingest_fund_nav(
        ctx,
        TiingoFundNav(http),
        TiingoNavTickers(http),
        until,
        since,
        **kwargs,  # type: ignore[arg-type]
    )


def stored(writer: StoreWriter) -> pd.DataFrame:
    frame = read_events(
        StoreReader(writer._backend), TABLE, date(2000, 1, 1), date(2030, 1, 1)
    ).frame
    return frame.sort_values(["instrument_id", "ts"]).reset_index(drop=True)


def test_funds_are_the_reference_cefs_and_closed_end_named_stocks_mapped_by_the_listing() -> None:
    reference = pd.DataFrame(FUNDS, columns=["symbol", "instrument_id", "security_type", "name"])
    assert list(reference[is_closed_end(reference)]["symbol"]) == [
        "PHK", "GDL", "JPS", "ADX", "CHY",
    ]  # fmt: skip
    funds, unmapped = map_funds(reference, parse_nav_tickers(payloads.nav_tickers_zip()))
    assert [(f.symbol, f.nav_symbol, f.instrument_id) for f in funds] == [
        ("GDL", "XGDLX", "EQ:GDL"), ("JPS", "XJPSX", "EQ:JPS"), ("PHK", "XPHKX", "EQ:PHK"),
    ]  # fmt: skip
    assert unmapped == ["ADX", "CHY"]  # no NAV series; CAT's XCATX is another fund: never mapped
    assert funds[1].end == date(2024, 10, 8)
    only, _ = map_funds(reference, parse_nav_tickers(payloads.nav_tickers_zip()), ["phk"])
    assert [f.symbol for f in only] == ["PHK"]


def test_nav_rows_are_stored_per_nav_date_under_the_funds_id_with_known_from(
    writer: StoreWriter,
) -> None:
    vendor = Vendor({"XPHKX": series(20), "XGDLX": series(10), "XCATX": series(1)})
    record = run(writer, vendor, since=date(2026, 10, 2))
    assert record.status is RunStatus.COMPLETE
    assert sorted(vendor.asked) == ["XGDLX", "XPHKX"]  # JPS ended; ADX / CHY / CAT unmapped
    stats = record.stats
    assert (stats["funds"], stats["mapped"], stats["ended"], stats["fetched"]) == (5, 3, 1, 2)
    assert (stats["unmapped_count"], stats["unmapped"]) == (2, ["ADX", "CHY"])
    assert (stats["rows"], stats["clipped_rows"], stats["latest_nav"]) == (6, 2, "2026-10-07")
    frame = stored(writer)
    phk = frame[frame["instrument_id"] == "EQ:PHK"]
    assert set(frame["instrument_id"]) == {"EQ:PHK", "EQ:GDL"}  # never an id of the NAV symbol
    assert list(phk["nav"]) == [21.0, 22.0, 23.0]  # 2026-09-30 is before the window
    assert list(phk["ts"].dt.date) == [date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)]
    assert list(phk["session_date"]) == list(phk["ts"].dt.date)
    assert list(phk["known_from"]) == [date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)]
    assert set(frame["series"]) == {"nav"} and set(frame["nav_symbol"]) == {"XPHKX", "XGDLX"}
    assert set(frame["source"]) == {"tiingo"} and frame["knowledge_ts"].min() > pd.Timestamp(FIXED)


def test_the_default_window_is_the_last_days_and_a_stored_nav_is_not_written_again(
    writer: StoreWriter,
) -> None:
    vendor = Vendor({"XPHKX": series(20), "XGDLX": series(10)})
    first = run(writer, vendor)
    assert first.stats["window"] == f"{UNTIL - timedelta(days=LOOKBACK_DAYS)}..{UNTIL}"
    assert first.stats["rows"] == 8  # 2026-09-30 is 8 days back: inside the 10-day window
    again = run(writer, vendor, force=True)  # the same NAVs: nothing to write
    assert (again.stats["rows"], again.stats["already_stored_rows"]) == (0, 8)
    restated = Vendor({"XPHKX": payloads.nav_prices([("2026-10-06", 99.0)]), "XGDLX": series(10)})
    third = run(writer, restated, force=True)
    assert third.stats["rows"] == 1  # a restated NAV is a later version, the others are skipped
    frame = stored(writer)
    assert (
        float(frame[(frame["instrument_id"] == "EQ:PHK") & (frame["nav"] == 99.0)]["nav"].iloc[0])
        == 99.0
    )
    assert len(frame) == 8  # one row per (fund, date): the restatement replaced 2026-10-06's


def test_a_finished_fund_is_not_fetched_again_without_force_and_an_unanswered_one_is(
    writer: StoreWriter,
) -> None:
    vendor = Vendor({"XPHKX": series(20)})  # XGDLX answers 404: NO_DATA, done
    run(writer, vendor, since=date(2026, 10, 2))
    assert sorted(vendor.asked) == ["XGDLX", "XPHKX"]
    second = run(writer, vendor, since=date(2026, 10, 2))
    assert sorted(vendor.asked) == ["XGDLX", "XPHKX"]  # nothing asked again
    assert second.stats["skipped_done"] == 2 and second.stats["pending"] == 0
    broken = Vendor({}, broken=("XGDLX", "XPHKX"))
    failed = run(writer, broken, since=date(2026, 10, 1), until=date(2026, 10, 7))
    assert failed.stats["items"] == {"FETCH_ERROR": 2}  # a different window: asked, not answered
    assert failed.stats["pending"] == 2  # a later run asks again
    assert (
        run(writer, vendor, since=date(2026, 10, 1), until=date(2026, 10, 7)).stats["pending"] == 0
    )


def test_the_month_budget_is_shared_with_bars_history_and_caps_the_run(writer: StoreWriter) -> None:
    started = datetime(2026, 10, 2, 9, tzinfo=UTC)
    spent = RunRecord("bars_history-spent", "bars_history", UNTIL, started)
    spent.status, spent.finished_at = RunStatus.COMPLETE, started
    spent.items = {f"hist:EQ:{i}": "OK: w" for i in range(9)}
    writer._backend.runs.save(spent)  # type: ignore[attr-defined]
    vendor = Vendor({"XPHKX": series(20), "XGDLX": series(10)})
    capped = run(
        writer, vendor, budget=10, clock=lambda: started + timedelta(days=14, minutes=next(TICKS))
    )
    assert capped.stats["fetched"] == 1 and capped.stats["pending"] == 1
    assert (capped.stats["month_used"], capped.stats["month_remaining"]) == (10, 0)
    assert len(vendor.asked) == 1  # one symbol left of the month's ten: one request
    none = run(
        writer, vendor, budget=10, clock=lambda: started + timedelta(days=15, minutes=next(TICKS))
    )
    assert none.stats["fetched"] == 0 and len(vendor.asked) == 1


def test_three_unanswered_funds_in_a_row_end_the_run_and_a_bad_window_is_refused(
    writer: StoreWriter,
) -> None:
    broken = Vendor({}, broken=("XGDLX", "XPHKX", "XJPSX"))
    record = run(writer, broken, since=date(2020, 1, 1))  # JPS's series is in the window too
    assert record.status is RunStatus.PARTIAL and len(broken.asked) == 3
    with pytest.raises(ValueError, match="before"):
        run(writer, Vendor({}), since=date(2026, 10, 17))


def test_the_task_name_is_the_one_the_budget_counts() -> None:
    assert TASK in TASKS


def test_nav_symbol_is_x_ticker_x_with_the_vendor_share_class_spelling() -> None:
    assert nav_symbol("phk") == "XPHKX"
    assert nav_symbol("BRK.B") == "XBRK-BX"


def test_a_restated_nav_is_known_from_the_restating_session_not_the_day_after() -> None:
    ts = pd.Timestamp("2026-10-06", tz="UTC")
    other = pd.Timestamp("2026-10-07", tz="UTC")
    nav = pd.DataFrame({"ts": [ts, other], "nav": [99.0, 5.0]})
    fund = Fund("PHK", "EQ:PHK", "XPHKX", date(2004, 3, 22), None)
    rows, _, same = nav_rows(nav, fund, date(2026, 10, 1), UNTIL, {ts: 20.0, other: 5.0}, UNTIL)
    assert same == 1 and list(rows["nav"]) == [99.0]
    assert list(rows["known_from"]) == [UNTIL]  # not 2026-10-07, the next session after the NAV
    fresh, _, _ = nav_rows(nav, fund, date(2026, 10, 1), UNTIL, {}, UNTIL)
    assert list(fresh["known_from"]) == [date(2026, 10, 7), date(2026, 10, 8)]
