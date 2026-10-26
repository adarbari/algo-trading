"""``option-history-import`` (ADR 0084): a folder of daily and monthly zips becomes one committed
run per session in the history store; ids from the index map and the strict listing resolver; a
session already held is skipped; the acceptance rules fail the batch, never silently."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.data.option_history import reading
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade_ingestion.tasks.options_history import importer
from algotrade_ingestion.tasks.options_history.importer import ImportOptions, import_history
from algotrade_sources.vendors.historicaloptiondata.files_source import HodFiles, hod_files
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.option_history.files import (
    DAY_ONE,
    DAY_TWO,
    FIXTURES,
    folder,
    main_store,
    make_zip,
    session_members,
)

TODAY = date(2026, 10, 26)
CLOCK_START = datetime(2026, 10, 26, 18, tzinfo=UTC)
WRITTEN = datetime(2026, 10, 26, 18, tzinfo=UTC)


class Clock:
    """A clock that moves a minute a call from the write instant (run ids carry the second)."""

    def __init__(self) -> None:
        self.now = WRITTEN

    def __call__(self) -> datetime:
        self.now += timedelta(minutes=1)
        return self.now


CLOCK = Clock()


def run_import(
    root: Path, history: MemoryBackend, options: ImportOptions | None = None, writer=None
):
    main = writer or main_store()
    ctx = task_ctx(main, clock=CLOCK, sources={"hod_files": HodFiles(root)})
    return import_history(ctx, TODAY, options or ImportOptions(), open_store=lambda url: history)


def test_two_sessions_from_a_daily_and_a_monthly_zip_become_two_committed_runs(
    tmp_path: Path,
) -> None:
    history = MemoryBackend()
    record = run_import(folder(tmp_path), history)
    reader = StoreReader(history)
    assert record.status is RunStatus.COMPLETE
    assert record.items == {"2019-08-15": "OK", "2019-08-16": "OK"}
    assert reading.sessions(reader) == [DAY_ONE, DAY_TWO]
    quotes = reading.option_quotes(reader, DAY_ONE)
    assert quotes is not None and len(quotes) == 37  # the four adjusted-series rows are out
    assert set(quotes["session_date"]) == {DAY_ONE}
    stamps = set(pd.to_datetime(quotes["knowledge_ts"], utc=True))
    assert len(stamps) == 1 and min(stamps) > pd.Timestamp(WRITTEN)  # the write, never the session
    assert list(quotes["symbol"]) == sorted(quotes["symbol"])  # sorted by symbol first
    assert reading.underlying_quotes(reader, DAY_TWO) is not None
    assert reading.option_stats(reader, DAY_TWO) is not None


def test_underlying_ids_are_indexes_by_map_listings_by_session_and_null_when_unknown(
    tmp_path: Path,
) -> None:
    history = MemoryBackend()
    run_import(folder(tmp_path), history)
    reader = StoreReader(history)
    day_one = reading.option_quotes(reader, DAY_ONE)
    assert day_one is not None
    ids = day_one.groupby("symbol")["underlying_id"].first().to_dict()
    assert ids == {"AAPL": "EQ:AAPL", "SPX": "IDX:SPX", "SPXW": "IDX:SPX", "SPY": "EQ:SPY"}
    stats_one = reading.underlying_quotes(reader, DAY_ONE)
    stats_two = reading.underlying_quotes(reader, DAY_TWO)
    assert stats_one is not None and stats_two is not None
    assert stats_one.set_index("symbol").loc["A", "underlying_id"] == "EQ:A"  # alive on day one
    assert pd.isna(stats_two.set_index("symbol").loc["A", "underlying_id"])  # delisted: null
    run = StoreReader(history).runs(reading.SESSION_TASK, DAY_TWO)[0]
    assert run.stats["unresolved_symbols"] == 0  # no option rows for A: only its stock quote


def test_a_read_of_one_underlying_returns_only_its_rows(tmp_path: Path) -> None:
    history = MemoryBackend()
    run_import(folder(tmp_path), history)
    spy = reading.option_quotes(StoreReader(history), DAY_TWO, ["spy"])
    assert spy is not None and set(spy["symbol"]) == {"SPY"} and len(spy) == 10
    assert reading.option_quotes(StoreReader(history), date(2019, 8, 14)) is None


def test_the_quality_counts_are_on_the_session_run(tmp_path: Path) -> None:
    history = MemoryBackend()
    run_import(folder(tmp_path), history)
    run = StoreReader(history).runs(reading.SESSION_TASK, DAY_ONE)[0]
    assert run.stats["rows"] == 37 and run.stats["nonstandard_series"] == 4
    assert run.stats["osi_mismatch"] == 1 and run.stats["crossed"] == 0
    assert run.stats["nonstandard_roots"] == "AAPL1:4"  # which roots were left out
    assert run.stats["zip"] == "Sample_L2_20190815.zip" and ":" in run.stats["checksum"]


def test_a_session_already_held_is_skipped_and_force_imports_it_again(tmp_path: Path) -> None:
    history = MemoryBackend()
    root = folder(tmp_path)
    run_import(root, history)
    again = run_import(root, history)
    assert again.stats["already_held"] == 2 and again.stats["imported"] == 0
    assert len(StoreReader(history).runs(reading.SESSION_TASK, DAY_ONE)) == 1
    run_import(root, history, ImportOptions(force=True))
    assert len(StoreReader(history).runs(reading.SESSION_TASK, DAY_ONE)) == 2


def test_a_dry_run_reports_and_writes_nothing(tmp_path: Path) -> None:
    history = MemoryBackend()
    record = run_import(folder(tmp_path), history, ImportOptions(dry_run=True))
    assert record.stats["rows"] == 74 and record.stats["dry_run"] is True
    assert record.stats["parsed"] == 2 and "imported" not in record.stats
    assert reading.sessions(StoreReader(history)) == []


def test_limit_and_range_choose_the_sessions(tmp_path: Path) -> None:
    history = MemoryBackend()
    root = folder(tmp_path)
    run_import(root, history, ImportOptions(limit=1))
    assert reading.sessions(StoreReader(history)) == [DAY_ONE]
    run_import(root, history, ImportOptions(start=DAY_TWO))
    assert reading.sessions(StoreReader(history)) == [DAY_ONE, DAY_TWO]


def test_a_day_that_is_not_an_exchange_session_fails_its_item_and_the_batch(
    tmp_path: Path,
) -> None:
    frame = pd.read_csv(FIXTURES / "options_20190816.csv")
    frame[" DataDate"] = "08/17/2019"
    members: dict[str, str | bytes] = {
        "options_20190817.csv": frame.to_csv(index=False).encode(),
        "stockquotes_20190817.csv": "stockquotes_20190816.csv",
    }
    make_zip(tmp_path / "sat.zip", members)
    history = MemoryBackend()
    record = run_import(tmp_path, history)
    assert record.status is RunStatus.FAILED
    assert "not an exchange session" in record.items["2019-08-17"]
    assert reading.sessions(StoreReader(history)) == []


def test_options_without_stockquotes_fail_the_session_but_earlier_ones_stay(tmp_path: Path) -> None:
    make_zip(tmp_path / "one.zip", session_members("20190815"))
    make_zip(tmp_path / "two.zip", {"options_20190816.csv": "options_20190816.csv"})
    history = MemoryBackend()
    record = run_import(tmp_path, history)
    assert record.status is RunStatus.FAILED and record.stats["failed"] == 1
    assert "no stockquotes" in record.items["2019-08-16"]
    assert reading.sessions(StoreReader(history)) == [DAY_ONE]


def test_a_folder_with_no_session_fails(tmp_path: Path) -> None:
    record = run_import(tmp_path, MemoryBackend())
    assert record.status is RunStatus.FAILED


def test_the_vendor_dividends_and_splits_are_stored_once_by_ex_date(tmp_path: Path) -> None:
    history = MemoryBackend()
    root = folder(tmp_path)
    record = run_import(root, history)
    reader = StoreReader(history)
    assert record.stats["actions_rows"] == 6
    dividends = reader.table(importer.DIVIDENDS, date(2019, 12, 30))
    assert dividends is not None and list(dividends["symbol"]) == ["AAPL"]
    assert reader.table(importer.SPLITS, date(2014, 3, 7)) is not None
    run_import(root, history, ImportOptions(force=True))
    assert len(reader.runs(importer.ACTIONS_TASK)) == 2


def test_the_history_store_gets_the_runs_and_the_main_store_none(tmp_path: Path) -> None:
    history, main = MemoryBackend(), main_store()
    run_import(folder(tmp_path), history, writer=main)
    assert StoreReader(main._backend).runs(importer.TASK) == []
    assert StoreReader(history).runs(importer.TASK)


def test_without_the_source_folder_the_task_says_so() -> None:
    ctx = task_ctx(main_store(), clock=lambda: WRITTEN, sources={"hod_files": hod_files()})
    with pytest.raises(ConfigurationError, match="--source-dir"):
        import_history(ctx, TODAY, ImportOptions(), open_store=lambda url: MemoryBackend())
