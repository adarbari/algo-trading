"""``history-copy`` (ADR 0060): market tables copied for every year, instrument tables for the
last years only, a night rebuilds only what changed, and a table is skipped (a WARN, never a
failure) below the disk floor, over the budget, or when its build cannot run."""

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from algotrade.config.site.nightly import HistoryCopySettings
from algotrade.config.site.settings import load_nightly
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.derived.history_copy import (
    GB,
    build_copies,
    check_history_copy,
    skip_reason,
)
from algotrade_ingestion.tasks.framework import registry
from algotrade_ingestion.tasks.framework.run import TaskContext
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.stored_frames import stamped

SESSION = date(2026, 3, 2)
MARKET = "rollups/market/demo@v1"
BARS = "rollups/instrument/demo@v1"
OTHER = "rollups/instrument/other@v1"


def _document(**keys: Any) -> dict[str, Any]:
    return {
        "history_copy": {
            "market_prefix": "rollups/market/",
            "instrument_tables": [BARS, OTHER],
            "recent_years": 2,
            **keys,
        },
    }


def _ctx(root: Path, **keys: Any) -> TaskContext:
    writer = StoreWriter(LocalBackend(root))
    configs = MemoryConfigStore({("site", "settings", "nightly"): _document(**keys)})
    for year in (2024, 2025, 2026):
        for n in range(3):
            day = date(year, 1, 5) + timedelta(days=n)
            for table, ids in ((MARKET, ["MKT:US"]), (BARS, ["EQ:A", "EQ:B"]), (OTHER, ["EQ:A"])):
                rows = [{"instrument_id": s, "a": float(n)} for s in ids]
                writer.write_table(table, day, "r1", stamped(rows, day, "r1"))
    return replace(task_ctx(writer), configs=configs)


def test_the_settings_come_from_nightly_toml_and_default_to_no_instrument_tables() -> None:
    store = MemoryConfigStore({("site", "settings", "nightly"): _document(budget_gb=1.5)})
    assert load_nightly(store).history_copy == HistoryCopySettings(
        market_prefix="rollups/market/", instrument_tables=(BARS, OTHER), budget_gb=1.5
    )
    assert load_nightly(MemoryConfigStore({})).history_copy.instrument_tables == ()


def test_market_tables_get_every_year_and_instrument_tables_the_last_years(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    record = build_copies(ctx, SESSION)
    assert record.stats["built"] == {
        MARKET: [2024, 2025, 2026],
        BARS: [2025, 2026],
        OTHER: [2025, 2026],
    }
    assert record.stats["skipped"] == {}
    assert ctx.writer.history_size(MARKET) > 0
    again = build_copies(ctx, SESSION)  # nothing changed: nothing rebuilt
    assert again.stats["built"] == {}


def test_a_night_rebuilds_only_the_year_that_changed_and_drops_the_year_that_left(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path)
    build_copies(ctx, SESSION)
    day = date(2026, 3, 2)
    ctx.writer.write_table(
        BARS, day, "r2", stamped([{"instrument_id": "EQ:A", "a": 9.0}], day, "r2")
    )
    assert build_copies(ctx, SESSION).stats["built"] == {BARS: [2026]}
    build_copies(ctx, date(2027, 1, 4))  # the window moves on: 2025 leaves, 2027 has no partitions
    years = ctx.writer._backend.tables.history.years(BARS)  # type: ignore[attr-defined]
    assert sorted(years) == [2026]


def test_a_table_is_skipped_below_the_disk_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, free_disk_floor_gb=10.0)
    monkeypatch.setattr(StoreWriter, "free_bytes", lambda self: 3 * GB)
    record = build_copies(ctx, SESSION)
    assert record.stats["built"] == {}
    assert set(record.stats["skipped"]) == {MARKET, BARS, OTHER}
    assert "below the 10.0 GB floor" in record.stats["skipped"][BARS]
    assert ctx.writer.history_size(BARS) == 0
    warns = check_history_copy(record.stats, SESSION)
    assert {c.status for c in warns} == {"WARN"} and len(warns) == 3


def test_the_floor_counts_the_copy_a_rebuild_keeps_beside_the_new_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, free_disk_floor_gb=1.0)
    build_copies(ctx, SESSION)
    held = ctx.writer.history_size(BARS)
    monkeypatch.setattr(StoreWriter, "free_bytes", lambda self: int(GB + held - 1))
    assert BARS in build_copies(ctx, SESSION).stats["skipped"]


def test_an_instrument_table_over_the_budget_is_not_started(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, budget_gb=1e-6)
    record = build_copies(ctx, SESSION)
    assert MARKET in record.stats["built"]  # market tables are not budgeted
    assert BARS in record.stats["built"]  # the first table starts: nothing is held yet
    assert OTHER in record.stats["skipped"] and "already hold" in record.stats["skipped"][OTHER]
    assert any(c.name == "history_copy_budget" for c in check_history_copy(record.stats, SESSION))


def test_a_build_that_raises_is_a_skip_not_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path)

    def broken(self: StoreWriter, table: str, years: object) -> list[int]:
        raise ValueError("no instrument_id column")

    monkeypatch.setattr(StoreWriter, "build_history", broken)
    record = build_copies(ctx, SESSION)
    assert record.stats["skipped"][MARKET] == "ValueError: no instrument_id column"
    assert record.status.value == "complete"


def test_the_step_is_registered_optional_and_can_be_switched_off(tmp_path: Path) -> None:
    from algotrade_ingestion.workflows.nightly.nightly import NIGHTLY  # noqa: PLC0415

    step = next(s for s in NIGHTLY if s.name == "history-copy")
    assert not step.critical and step.latest_only
    assert {"bars", "rollups", "market-rollups"} <= set(step.needs)
    assert registry.TASKS["history-copy"].tables == ()
    on = _ctx(tmp_path)
    assert skip_reason(on) is None
    off = replace(
        on, configs=MemoryConfigStore({("site", "settings", "nightly"): _document(enabled=False)})
    )
    assert skip_reason(off) == "skipped: [history_copy] enabled = false"
