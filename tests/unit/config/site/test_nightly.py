"""The nightly's site config (``algotrade.config.site.nightly``): its history copy covers what the
Explore history reads."""

import tomllib

import pytest

from algotrade.config.site.settings import NightlySettings, load_nightly
from algotrade.core.model.errors import ConfigurationError
from algotrade.features.registry import GROUPS
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.tables.schemas.registry import spec_for
from tests.conftest import REPO_ROOT


def test_the_history_copy_holds_every_instrument_table_a_feature_history_reads() -> None:
    # Explore's Features tab asks 6 histories of 3 months: without a copy each reads one
    # whole-market partition per session per table (1 to 2.8 s a request, 11.6 s a ticker)
    copied = set(
        load_nightly(
            FileConfigStore(REPO_ROOT / "config", local=False)
        ).history_copy.instrument_tables
    )
    stored = {g.table for g in GROUPS.values() if g.entity == "instrument"}
    assert stored - copied == set(), "add these tables to [history_copy] instrument_tables"


def test_every_declared_backfill_names_a_stored_rollup_table() -> None:
    declared = load_nightly(FileConfigStore(REPO_ROOT / "config", local=False)).backfilling
    stored = {g.table for g in GROUPS.values()}
    assert set(declared) <= stored


@pytest.mark.parametrize(
    "entry",
    [
        '"bars/1d" = { until = "2026-11-03", reason = "x" }',  # not a rollup table
        '"rollups/instrument/etf_launches@v1" = { reason = "x" }',  # no until
        '"rollups/instrument/etf_launches@v1" = { until = "soon", reason = "x" }',
        '"rollups/instrument/etf_launches@v1" = { until = "2026-11-03" }',  # no reason
    ],
)
def test_a_malformed_backfill_entry_is_refused(entry: str) -> None:
    with pytest.raises(ConfigurationError):
        NightlySettings.from_document(tomllib.loads(f"[backfilling]\n{entry}\n"))


def test_compaction_lists_only_merge_tables_without_a_history_copy() -> None:
    # ADR 0078: the history copy signs the index (inode, mtime, size), so a swap would void it;
    # a snapshot table keeps one run, so there is nothing to merge
    nightly = load_nightly(FileConfigStore(REPO_ROOT / "config", local=False))
    copied = nightly.history_copy
    assert nightly.compaction.tables == ("outcomes/instrument/forward_returns@v2",)
    for table in nightly.compaction.tables:
        assert spec_for(table).runs == "merge", f"{table} is not a merge-mode table"
        assert table not in copied.instrument_tables, f"{table} has a history copy declared"
        assert not (copied.market_prefix and table.startswith(copied.market_prefix)), table


def test_the_shipped_warm_ceiling_is_3000_mb_and_a_bad_one_is_refused() -> None:
    assert load_nightly(FileConfigStore(REPO_ROOT / "config", local=False)).warm_ceiling_mb == 3000
    doc = {"serving": {"warm_ceiling_mb": 1500}}
    assert NightlySettings.from_document(doc).warm_ceiling_mb == 1500
    with pytest.raises(ConfigurationError):
        NightlySettings.from_document({"serving": {"warm_ceiling_mb": 0}})
