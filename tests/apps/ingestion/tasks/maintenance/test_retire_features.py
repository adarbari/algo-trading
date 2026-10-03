"""``retire-features``: a superseded group's table is deleted only once its replacement has
every session it has; a dry run reports sessions and sizes and deletes nothing."""

from datetime import date
from pathlib import Path

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.maintenance.retire_features import retire
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.rollup_store import write_rows

D1, D2, TODAY = date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2)
OLD, NEW = "rollups/instrument/price_stats@v1", "rollups/instrument/price_stats@v2"


def _store(root: Path) -> tuple[StoreWriter, StoreReader]:
    backend = LocalBackend(root)
    writer = StoreWriter(backend)
    for day in (D1, D2):
        write_rows(writer, OLD, day, [{"instrument_id": "EQ:A", "close": 1.0, "pct": 0.1}])
    write_rows(writer, NEW, D2, [{"instrument_id": "EQ:A", "close": 1.0}])
    return writer, StoreReader(backend)


def test_refuses_until_the_replacement_covers_every_session(tmp_path: Path) -> None:
    writer, reader = _store(tmp_path)
    ctx = task_ctx(writer, reader)
    with pytest.raises(ConfigurationError, match=r"lacks 1 of .*'2026-09-30'.*--from 2026-09-30"):
        retire(ctx, TODAY, "price_stats@v1")
    assert reader.dates(OLD) == [D1, D2]
    failed = reader.runs("retire_features")[-1]
    assert failed.status is RunStatus.FAILED and failed.stats["uncovered"] == 1
    with pytest.raises(ConfigurationError, match="not a superseded feature group"):
        retire(ctx, TODAY, "price_stats@v2")


def test_dry_run_then_delete(tmp_path: Path) -> None:
    writer, reader = _store(tmp_path)
    write_rows(writer, NEW, D1, [{"instrument_id": "EQ:A", "close": 1.0}])
    ctx = task_ctx(writer, reader)
    dry = retire(ctx, TODAY, "price_stats@v1", dry_run=True)
    assert dry.status is RunStatus.COMPLETE
    assert (dry.stats["sessions"], dry.stats["first"], dry.stats["last"]) == (
        2,
        "2026-09-30",
        "2026-10-01",
    )
    assert dry.stats["bytes"] > 0 and dry.stats["replacement_bytes"] > 0
    assert "bytes_freed" not in dry.stats and reader.dates(OLD) == [D1, D2]
    done = retire(ctx, TODAY, "price_stats@v1")
    assert done.stats["partitions_deleted"] == 2 and done.stats["bytes_freed"] == dry.stats["bytes"]
    assert reader.dates(OLD) == [] and reader.dates(NEW) == [D1, D2]
    assert not (tmp_path / "tables" / OLD).exists()
