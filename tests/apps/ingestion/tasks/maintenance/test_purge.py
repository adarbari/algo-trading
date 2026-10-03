"""``purge-raw``: raw responses kept per source (its section's ``raw_retention_days``, else
the global window; ``--keep-days`` overrides all), staging and uncommitted writes by age."""

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.sources.framework.registry import RAW_SECTIONS
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.maintenance.purge import purge, raw_keep_days
from tests.ingest_helpers import task_ctx

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
