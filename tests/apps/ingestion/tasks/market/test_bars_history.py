import dataclasses
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from itertools import count
from pathlib import Path

import pandas as pd
import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.data import StoreReader
from algotrade.services.events.fill import IV_HISTORY, PRICE_STATS
from algotrade.services.events.scope import LIQUIDITY
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.market.bars_history import (
    ingest_bars_history,
    split_findings,
)
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.tiingo.prices import TiingoDailyPrices
from tests.helpers.ingest_fakes import FIXED, http_for, task_ctx
from tests.helpers.payloads import tiingo as payloads
from tests.helpers.rollup_store import write_split
from tests.helpers.stored_frames import stamped, write_reference

SINCE, UNTIL = date(2020, 1, 1), date(2020, 1, 7)
DAYS = ["2020-01-02", "2020-01-03", "2020-01-06"]
IDS = {"AAA": "EQ:AAA", "BBB": "EQ:BBB", "CCC": "EQ:CCC"}
BARS = "bars/1d"


class Vendor:
    """Answers Tiingo requests from a ticker -> payload map; a ticker not in it is a 404; a
    ticker in ``broken`` a server error. Counts the tickers asked."""

    def __init__(self, payloads_by_ticker: Mapping[str, bytes], broken: tuple[str, ...] = ()):
        self.payloads, self.broken, self.asked = dict(payloads_by_ticker), broken, []

    def __call__(self, url: str) -> bytes:
        ticker = url.split("/daily/")[1].split("/", maxsplit=1)[0]
        self.asked.append(ticker)
        if ticker in self.broken:
            raise HttpError(500)
        if ticker not in self.payloads:
            raise HttpError(404)
        return self.payloads[ticker]


type Row = tuple[str, float, float, float, float, float]


def rows(base: float, days: list[str] = DAYS) -> list[Row]:
    return [(d, base, base + 1, base - 1, base + 0.5, 1000.0) for d in days]


@pytest.fixture(params=["memory", "local"])
def writer(request: pytest.FixtureRequest, tmp_path: Path) -> StoreWriter:
    """A store with the reference loaded, on both backends (Parquet reads what it wrote)."""
    backend = MemoryBackend() if request.param == "memory" else LocalBackend(tmp_path / "data")
    writer = StoreWriter(backend)
    write_reference(writer, date(2020, 1, 1), IDS)
    return writer


TICKS = count()  # one clock across the runs of a test: run ids and knowledge_ts never repeat


def advancing_clock() -> datetime:
    return FIXED + timedelta(minutes=next(TICKS))


def run(
    writer: StoreWriter,
    vendor: Vendor,
    symbols: tuple[str, ...] = ("AAA", "BBB"),
    **kwargs: object,
) -> RunRecord:
    source = TiingoDailyPrices(http_for(vendor, RetryPolicy(tries=1)))
    ctx = task_ctx(writer, clock=advancing_clock)
    return ingest_bars_history(ctx, source, symbols, SINCE, UNTIL, **kwargs)  # type: ignore[arg-type]


def stored(writer: StoreWriter, day: str) -> pd.DataFrame:
    frame = StoreReader(writer._backend).table(BARS, date.fromisoformat(day))
    assert frame is not None
    return frame.sort_values("instrument_id").reset_index(drop=True)


def write_massive(writer: StoreWriter, day: str, ids: list[str]) -> None:
    """A Massive partition (with its vwap) written an earlier day than any of these runs."""
    when = date.fromisoformat(day)
    table = [
        {
            "instrument_id": i,
            "ts": pd.Timestamp(when, tz="UTC") + pd.Timedelta(hours=4),
            "open": 50.0, "high": 52.0, "low": 49.0, "close": 51.0, "volume": 9.0, "vwap": 50.5,
        }
        for i in ids
    ]  # fmt: skip
    frame = stamped(table, when, "massive-run", datetime(2020, 1, 1, tzinfo=UTC), "massive")
    writer.write_table(BARS, when, "massive-run", frame)


def test_writes_unadjusted_bars_one_partition_per_session(writer: StoreWriter) -> None:
    vendor = Vendor({"AAA": payloads.prices(rows(10)), "BBB": payloads.prices(rows(20))})
    record = run(writer, vendor)
    assert record.status is RunStatus.COMPLETE
    assert vendor.asked == ["AAA", "BBB"]  # one request per symbol
    for day in DAYS:
        frame = stored(writer, day)
        assert list(frame["instrument_id"]) == ["EQ:AAA", "EQ:BBB"]
        assert set(frame["source"]) == {"tiingo"}
        assert list(frame["close"]) == [10.5, 20.5]  # the unadjusted close, not adjClose
    assert StoreReader(writer._backend).dates(BARS) == [date.fromisoformat(d) for d in DAYS]
    stats = record.stats
    assert (stats["sessions_written"], stats["rows"], stats["fetched"]) == (3, 6, 2)
    assert (stats["overlap_rows"], stats["split_mismatches"], stats["pending"]) == (0, 0, 0)
    assert stats["window"] == "2020-01-01..2020-01-07" and stats["licence"] == "personal"


def test_unknown_symbols_are_reported_never_fetched(writer: StoreWriter) -> None:
    vendor = Vendor({"AAA": payloads.prices(rows(10))})
    record = run(writer, vendor, ("AAA", "ZZZ", "aaa"))
    assert vendor.asked == ["AAA"]
    assert record.stats["unknown_symbols"] == ["ZZZ"] and record.stats["symbols"] == 2
    assert record.items["sym:ZZZ"].startswith("UNKNOWN: not in the reference of 2020-01-01")
    assert record.status is RunStatus.COMPLETE


def test_the_scope_is_the_list_and_the_requested_and_with_tiers_the_tier_names(
    writer: StoreWriter,
) -> None:
    """One owner resolves it (``services.events``): the site list and ``--symbols``; the names
    whose short puts are tier A / B on the newest stored session on or before ``--until`` only
    with ``include_tiers`` (they need Tiingo's Power tier)."""
    day = date(2020, 1, 2)
    tiers = [{"instrument_id": "EQ:BBB", "short_put_ok": True},
             {"instrument_id": "EQ:CCC", "short_put_ok": False}]  # fmt: skip
    writer.write_table(LIQUIDITY, day, "t", stamped(tiers, day, "t"))
    scope = {("site", "events", "scope"): {"name": [{"symbol": "AAA", "added_on": day}]}}
    ctx = dataclasses.replace(
        task_ctx(writer, clock=advancing_clock), configs=MemoryConfigStore(scope)
    )

    def fetch(**kwargs: bool) -> tuple[list[str], RunRecord]:
        vendor = Vendor({s: payloads.prices(rows(10)) for s in ("AAA", "BBB", "CCC")})
        source = TiingoDailyPrices(http_for(vendor, RetryPolicy(tries=1)))
        record = ingest_bars_history(ctx, source, ("CCC",), SINCE, UNTIL, **kwargs)
        return vendor.asked, record

    asked, record = fetch()
    assert asked == ["AAA", "CCC"]  # the list, then the requested: no tier names by default
    assert record.stats["by_reason"] == {"list": 1, "requested": 1}
    assert record.stats["tier_session"] is None
    asked, record = fetch(include_tiers=True, force=True)
    assert asked == ["AAA", "CCC", "BBB"]  # then the tier names
    assert record.stats["by_reason"] == {"list": 1, "requested": 1, "tier": 1}
    assert record.stats["tier_session"] == day and record.stats["symbols"] == 3


def test_a_row_massive_already_holds_is_kept_and_counted(writer: StoreWriter) -> None:
    for day in DAYS:
        write_massive(writer, day, ["EQ:AAA", "EQ:CCC"])
    vendor = Vendor({"AAA": payloads.prices(rows(10)), "BBB": payloads.prices(rows(20))})
    record = run(writer, vendor)
    assert (record.stats["overlap_rows"], record.stats["rows"]) == (3, 3)
    frame = stored(writer, DAYS[0])
    assert list(frame["instrument_id"]) == ["EQ:AAA", "EQ:BBB", "EQ:CCC"]
    assert list(frame["source"]) == ["massive", "tiingo", "massive"]
    assert list(frame["close"]) == [51.0, 20.5, 51.0]  # Massive's AAA stands
    assert frame["vwap"].notna().tolist() == [True, False, True]
    # Massive's rows are carried over as they were stored, never restamped as this run's
    assert list(frame["run_id"])[0::2] == ["massive-run", "massive-run"]
    assert list(frame["run_id"])[1] == record.run_id
    massive_known = pd.Timestamp("2020-01-01", tz="UTC")
    assert frame["knowledge_ts"][0] == frame["knowledge_ts"][2] == massive_known
    assert frame["knowledge_ts"][1] > frame["knowledge_ts"][0]


def test_a_missing_session_in_massives_window_is_left_for_the_nightly(writer: StoreWriter) -> None:
    write_massive(writer, DAYS[1], ["EQ:CCC"])  # Massive's earliest partition: 2020-01-03
    vendor = Vendor({"AAA": payloads.prices(rows(10))})
    record = run(writer, vendor, ("AAA",))
    assert StoreReader(writer._backend).dates(BARS) == [date(2020, 1, 2), date(2020, 1, 3)]
    assert list(stored(writer, DAYS[1])["instrument_id"]) == ["EQ:AAA", "EQ:CCC"]
    assert record.stats["no_partition_rows"] == 1  # 2020-01-06: the gap a Massive run fills
    assert record.stats["rows"] == 2


def test_a_name_fetched_for_the_window_is_skipped_until_forced(writer: StoreWriter) -> None:
    vendor = Vendor({"AAA": payloads.prices(rows(10)), "BBB": payloads.prices(rows(20))})
    run(writer, vendor, ("AAA",))
    second = run(writer, vendor, ("AAA", "BBB"))
    assert vendor.asked == ["AAA", "BBB"]  # AAA was not asked again
    assert second.stats["skipped_done"] == 1 and second.stats["rows"] == 3
    third = run(writer, vendor, ("AAA", "BBB"))
    assert vendor.asked == ["AAA", "BBB"] and third.stats["fetched"] == 0
    forced = run(writer, vendor, ("AAA", "BBB"), force=True)
    assert vendor.asked == ["AAA", "BBB", "AAA", "BBB"]
    assert (forced.stats["already_stored_rows"], forced.stats["overlap_rows"]) == (6, 0)
    assert forced.stats["rows"] == 0 and forced.stats["sessions_written"] == 0
    assert list(stored(writer, DAYS[0])["close"]) == [10.5, 20.5]


def test_a_wider_window_than_an_earlier_run_fetches_again(writer: StoreWriter) -> None:
    vendor = Vendor({"AAA": payloads.prices(rows(10))})
    run(writer, vendor, ("AAA",))
    source = TiingoDailyPrices(http_for(vendor, RetryPolicy(tries=1)))
    ingest_bars_history(task_ctx(writer), source, ("AAA",), date(2019, 1, 1), UNTIL)
    assert vendor.asked == ["AAA", "AAA"]


def test_failed_names_are_retried_and_unknown_tickers_are_final(writer: StoreWriter) -> None:
    vendor = Vendor({"AAA": payloads.prices(rows(10))}, broken=("BBB",))
    first = run(writer, vendor, ("AAA", "BBB", "CCC"))
    assert first.status is RunStatus.PARTIAL
    assert first.items["hist:EQ:BBB"].startswith("FETCH_ERROR")
    assert first.items["hist:EQ:CCC"].startswith("NO_DATA")  # Tiingo answers 404
    assert first.stats["pending"] == 1 and first.stats["rows"] == 3
    vendor.broken = ()
    vendor.payloads["BBB"] = payloads.prices(rows(20))
    second = run(writer, vendor, ("AAA", "BBB", "CCC"))
    assert vendor.asked == ["AAA", "BBB", "CCC", "BBB"]
    assert second.status is RunStatus.COMPLETE and second.stats["rows"] == 3


def test_the_run_stops_after_names_tiingo_did_not_answer_in_a_row(writer: StoreWriter) -> None:
    vendor = Vendor({}, broken=("AAA", "BBB", "CCC", "DDD"))
    write_reference(writer, date(2020, 1, 2), {**IDS, "DDD": "EQ:DDD"}, run_id="ref2")
    record = run(writer, vendor, ("AAA", "BBB", "CCC", "DDD"))
    assert vendor.asked == ["AAA", "BBB", "CCC"]
    assert record.status is RunStatus.PARTIAL and record.stats["pending"] == 4
    assert "stopped" in record.stats["partial"][0]


def test_limit_caps_the_names_of_a_run(writer: StoreWriter) -> None:
    vendor = Vendor({s: payloads.prices(rows(10)) for s in IDS})
    record = run(writer, vendor, ("AAA", "BBB", "CCC"), limit=2)
    assert vendor.asked == ["AAA", "BBB"] and record.stats["pending"] == 1
    assert record.stats["eta_h"] == 0.0  # 72 s each


def test_split_check_reports_differences_and_still_writes(writer: StoreWriter) -> None:
    split_days = {"2020-01-03": 4.0}
    vendor = Vendor(
        {
            "AAA": payloads.prices(rows(10), split_days),  # events/split agrees
            "BBB": payloads.prices(rows(20), split_days),  # events/split has 2, not 4
            "CCC": payloads.prices(rows(30)),  # events/split has a split Tiingo does not show
        }
    )
    write_split(writer, "EQ:AAA", date(2020, 1, 3), 4.0, date(2020, 1, 4))  # a run each
    write_split(writer, "EQ:BBB", date(2020, 1, 3), 2.0, date(2020, 1, 5))
    write_split(writer, "EQ:CCC", date(2020, 1, 6), 2.0, date(2020, 1, 7))
    record = run(writer, vendor, ("AAA", "BBB", "CCC"))
    assert record.stats["split_mismatches"] == 2 and record.stats["rows"] == 9  # written anyway
    assert "split:EQ:AAA" not in record.items
    assert "tiingo 4 vs events/split 2" in record.items["split:EQ:BBB"]
    assert "tiingo none vs events/split 2" in record.items["split:EQ:CCC"]
    assert len(record.stats["split_mismatch_examples"]) == 2
    assert record.status is RunStatus.COMPLETE  # a finding, not a failure


def test_split_findings_only_compare_the_span_of_the_fetched_bars() -> None:
    tiingo = pd.DataFrame(
        {"ts": [pd.Timestamp("2020-01-03", tz="UTC")], "split_factor": [2.0], "div_cash": [0.0]}
    )
    stored = pd.DataFrame(
        {
            "ts": [pd.Timestamp(d, tz="UTC") for d in ("2019-06-03", "2020-01-03", "2020-02-03")],
            "ratio": [3.0, 2.0005, 5.0],  # within the tolerance; before and after the bars
        }
    )
    assert split_findings(tiingo, stored, date(2020, 1, 2), date(2020, 1, 6)) == []
    assert split_findings(tiingo, stored, date(2019, 1, 1), date(2020, 1, 6)) == [
        "2019-06-03: tiingo none vs events/split 3"
    ]


FILL_IDS = {s: f"EQ:{s}" for s in ("AAA", "BBB", "CCC", "DDD", "EEE")}


def fill_world() -> tuple[StoreWriter, Vendor]:
    """Five names; optionable CCC (iv 80) and EEE (iv 50), then BBB (adv 9e6), AAA, DDD."""
    writer = StoreWriter(MemoryBackend())
    write_reference(writer, date(2020, 1, 1), FILL_IDS)
    day = date(2020, 1, 2)
    tables = {
        LIQUIDITY: [{"instrument_id": "EQ:CCC"}, {"instrument_id": "EQ:EEE"}],
        IV_HISTORY: [{"instrument_id": "EQ:EEE", "iv30": 50.0},
                     {"instrument_id": "EQ:CCC", "iv30": 80.0}],
        PRICE_STATS: [{"instrument_id": "EQ:AAA", "adv_usd_20d": 5e6},
                      {"instrument_id": "EQ:BBB", "adv_usd_20d": 9e6}],
    }  # fmt: skip
    for table, found in tables.items():
        writer.write_table(table, day, "t", stamped(found, day, "t"))
    return writer, Vendor({s: payloads.prices(rows(10)) for s in FILL_IDS})


def fill_run(
    writer: StoreWriter,
    vendor: Vendor,
    fill: int,
    now: datetime,
    budget: int = 450,
) -> RunRecord:
    """A ``--fill`` run at ``now`` with the month's symbol budget ``budget``."""
    ctx = task_ctx(
        writer,
        clock=lambda: now + timedelta(seconds=next(TICKS)),  # run ids never repeat
        settings=SourcesSettings(tiingo_monthly_symbol_budget=budget),
    )
    source = TiingoDailyPrices(http_for(vendor, RetryPolicy(tries=1)))
    return ingest_bars_history(ctx, source, (), SINCE, UNTIL, fill=fill)


JAN, FEB = datetime(2020, 1, 10, 9, tzinfo=UTC), datetime(2020, 2, 2, 9, tzinfo=UTC)


def test_fill_takes_the_most_useful_names_without_history_and_skips_stored_ones() -> None:
    writer, vendor = fill_world()
    first = fill_run(writer, vendor, 2, JAN)
    assert vendor.asked == ["CCC", "EEE"]  # optionable, IV30 descending
    assert first.stats["filled"] == 2 and first.stats["by_reason"] == {"requested": 2}
    second = fill_run(writer, vendor, 2, JAN)
    assert vendor.asked == ["CCC", "EEE", "BBB", "AAA"]  # CCC / EEE have history: next two
    assert second.stats["filled"] == 2 and second.stats["skipped_done"] == 0
    third = fill_run(writer, vendor, 5, JAN)
    assert vendor.asked[-1] == "DDD" and third.stats["filled"] == 1
    assert fill_run(writer, vendor, 5, JAN).stats["filled"] == 0  # the universe is covered


def test_the_monthly_budget_counts_every_run_of_the_month_and_resets_in_the_next() -> None:
    writer, vendor = fill_world()
    first = fill_run(writer, vendor, 2, JAN, budget=3)
    assert first.stats["month_budget"] == 3 and first.stats["month_used"] == 2
    second = fill_run(writer, vendor, 5, JAN, budget=3)  # asks for 5, 1 of the 3 is left
    assert vendor.asked == ["CCC", "EEE", "BBB"]
    assert (second.stats["fetched"], second.stats["filled"]) == (1, 1)
    assert (second.stats["month_used"], second.stats["month_remaining"]) == (3, 0)
    capped = fill_run(writer, vendor, 5, JAN, budget=3)
    assert capped.stats["fetched"] == 0 and capped.stats["month_remaining"] == 0
    assert vendor.asked == ["CCC", "EEE", "BBB"]  # nothing asked of Tiingo
    february = fill_run(writer, vendor, 5, FEB, budget=3)  # a new month: the budget is whole
    assert vendor.asked == ["CCC", "EEE", "BBB", "AAA", "DDD"]
    assert (february.stats["month_used"], february.stats["month_remaining"]) == (2, 1)


def spent(
    writer: StoreWriter, started: datetime, finished: datetime | None, status: RunStatus, n: int
) -> None:
    """An earlier run of the task, with ``n`` ``hist:`` items (one of them a FETCH_ERROR)."""
    record = RunRecord(f"bars_history-x{n}-{started:%Y%m%dT%H%M}", "bars_history", UNTIL, started)
    record.status, record.finished_at = status, finished
    record.items = {f"hist:EQ:OLD{i}": "OK: w" for i in range(n - 1)} | {
        f"hist:EQ:ERR{n}": "FETCH_ERROR: HTTP 500"
    }
    writer._backend.runs.save(record)  # type: ignore[attr-defined]


def test_a_failed_run_this_month_has_spent_its_requests() -> None:
    """A run that crashed after its fetches (FAILED, FETCH_ERROR items included) counts."""
    writer, vendor = fill_world()
    spent(writer, JAN - timedelta(days=3), None, RunStatus.FAILED, 3)
    record = fill_run(writer, vendor, 5, JAN, budget=5)
    assert record.stats["fetched"] == 2 and vendor.asked == ["CCC", "EEE"]
    assert (record.stats["month_used"], record.stats["month_remaining"]) == (5, 0)


def test_a_run_spanning_a_month_end_counts_in_both_months() -> None:
    writer, vendor = fill_world()
    start, end = datetime(2020, 1, 31, 20, tzinfo=UTC), datetime(2020, 2, 1, 5, tzinfo=UTC)
    spent(writer, start, end, RunStatus.COMPLETE, 3)
    spent(writer, start, None, RunStatus.RUNNING, 1)  # crashed mid-run: still open: counts too
    in_feb = fill_run(writer, vendor, 5, FEB, budget=5)
    assert in_feb.stats["fetched"] == 1  # 3 + 1 of the 5 spent
    in_mar = fill_run(writer, vendor, 5, datetime(2020, 3, 5, tzinfo=UTC), budget=5)
    assert in_mar.stats["month_used"] == in_mar.stats["fetched"] + 1  # only the open run spills
