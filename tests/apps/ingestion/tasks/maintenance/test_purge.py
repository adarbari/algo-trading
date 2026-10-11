"""``purge-raw``: raw responses kept per source (its section's ``raw_retention_days``, else
the global window; ``--keep-days`` overrides all), staging and uncommitted writes by age, and the
edge trade ledger after 45 days but for the runs the run reader keeps (ADR 0064)."""

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.data import StoreReader
from algotrade.data.chains import LIVE_OPTION_QUOTES
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.edge_schemas import EDGE_TRADES
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.maintenance.purge import purge, raw_keep_days
from algotrade_sources.framework.registry import RAW_SECTIONS
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.stored_frames import stamped
from tests.unit.services.read.evaluation.conftest import DOCS
from tests.unit.services.read.evaluation.test_ledger import ROWS, write_ledger

SESSION = date(2026, 10, 30)
SETTINGS = SourcesSettings.from_document(
    {"raw_retention_days": 90, "sec_edgar": {"raw_retention_days": 7}}
)


def test_windows_come_from_each_raw_sources_section() -> None:
    sources = ["cboe_delayed", "sec_edgar", "synthetic"]
    assert raw_keep_days(SETTINGS, sources, RAW_SECTIONS) == {
        "cboe_delayed": 90,  # [cboe] sets none: the global window
        "sec_edgar": 7,
        "synthetic": 90,  # not a registry source: the global window
    }
    assert raw_keep_days(SETTINGS, sources, RAW_SECTIONS, 0) == dict.fromkeys(sources, 0)
    assert raw_keep_days(SourcesSettings(), ["sec_edgar"], RAW_SECTIONS) == {"sec_edgar": 90}


def ctx(writer: StoreWriter) -> TaskContext:
    return replace(task_ctx(writer, settings=SETTINGS), raw_sections=RAW_SECTIONS)


@pytest.mark.parametrize("kind", ["memory", "local"])
def test_purge_applies_retention_per_source(kind: str, tmp_path: Path) -> None:
    backend = MemoryBackend() if kind == "memory" else LocalBackend(tmp_path)
    writer = StoreWriter(backend)
    for source, dataset in (("sec_edgar", "companyfacts"), ("cboe_delayed", "option_chain")):
        for age in (1, 10, 100):
            writer.raw.put(source, dataset, SESSION - timedelta(age), "r", "k", b"{}")
    record = purge(ctx(writer), SESSION)
    assert record.stats["raw_files_removed_by_source"] == {"cboe_delayed": 1, "sec_edgar": 2}
    assert record.stats["raw_files_removed"] == 3
    assert record.stats["raw_keep_days"] == {"cboe_delayed": 90, "sec_edgar": 7}
    assert writer.raw.get("sec_edgar", "companyfacts", SESSION - timedelta(1), "r", "k")
    assert writer.raw.get("cboe_delayed", "option_chain", SESSION - timedelta(10), "r", "k")
    everything = purge(ctx(writer), SESSION, keep_days=0)
    assert everything.stats["raw_files_removed_by_source"] == {"cboe_delayed": 2, "sec_edgar": 1}
    assert everything.stats["keep_days"] == 0


def _live_rows(day: date) -> pd.DataFrame:
    row = {
        "instrument_id": "OPT:A:100", "underlying_id": "EQ:A", "symbol": "A",
        "ts": pd.Timestamp(day.isoformat(), tz="UTC"), "expiry": date(2026, 12, 18),
        "right": "C", "strike": 100.0, "bid": 1.0, "ask": 1.1, "last": None, "close": 1.0,
        "volume": 3.0, "iv": 0.3, "delta": 0.5, "conid": 7, "market_data_type": 3,
    }  # fmt: skip
    return stamped([row], day, f"live-{day}", source="ibkr")


@pytest.mark.parametrize("kind", ["memory", "local"])
def test_purge_keeps_live_option_quotes_seven_days(kind: str, tmp_path: Path) -> None:
    backend = MemoryBackend() if kind == "memory" else LocalBackend(tmp_path)
    writer, reader = StoreWriter(backend), StoreReader(backend)
    ages = (1, 6, 7, 8, 30)
    for age in ages:
        day = SESSION - timedelta(age)
        writer.write_table(LIVE_OPTION_QUOTES, day, f"live-{day}", _live_rows(day))
    other = SESSION - timedelta(30)
    writer.write_table("catalog/demo", other, "r", stamped([{"instrument_id": "EQ:A"}], other, "r"))
    record = purge(ctx(writer), SESSION)
    assert SourcesSettings().live_retention_days == 7
    assert record.stats["live_partitions_removed"] == 2 and record.stats["live_keep_days"] == 7
    assert reader.dates(LIVE_OPTION_QUOTES) == [SESSION - timedelta(a) for a in (7, 6, 1)]
    assert reader.dates("catalog/demo") == [other]  # only live/option_quotes is purged
    assert purge(ctx(writer), SESSION).stats["live_partitions_removed"] == 0


def test_purge_keeps_the_ledger_45_days_and_the_kept_runs_partitions() -> None:
    """Runs finished on 2026-10-02 (``T``): 45 days later only the range ends before the cutoff
    are candidates, and of those the canonical and latest run's partition is spared."""
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    session = date(2026, 12, 15)  # cutoff 2026-10-31: every run finished before it
    old, kept, recent = date(2026, 9, 1), date(2026, 9, 15), date(2026, 12, 5)
    write_ledger(backend, "old", ROWS, end=old, minutes=1)  # superseded by "latest"
    write_ledger(backend, "recent", ROWS, end=recent, split=None, minutes=2)
    write_ledger(backend, "latest", ROWS, end=kept, minutes=3)  # canonical and latest
    assert purge(ctx(writer), session).stats["ledger_partitions_removed"] is None  # no configs
    with_configs = replace(ctx(writer), configs=MemoryConfigStore(DOCS))
    assert purge(with_configs, session).stats["ledger_partitions_removed"] == 1
    assert reader.dates(EDGE_TRADES.name) == [kept, recent]


def test_purge_spares_a_run_finished_within_the_window_whatever_its_range_end() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    write_ledger(backend, "old", ROWS, end=date(2026, 6, 1), minutes=1)  # finished 2026-10-02
    write_ledger(backend, "latest", ROWS, end=date(2026, 7, 1), minutes=3)
    with_configs = replace(ctx(writer), configs=MemoryConfigStore(DOCS))
    assert purge(with_configs, SESSION).stats["ledger_partitions_removed"] == 0
    assert reader.dates(EDGE_TRADES.name) == [date(2026, 6, 1), date(2026, 7, 1)]
