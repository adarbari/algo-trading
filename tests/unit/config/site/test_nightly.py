"""The nightly's site config (``algotrade.config.site.nightly``): its history copy covers what the
Explore history reads."""

import tomllib

import pytest

from algotrade.config.site.settings import NightlySettings, load_nightly
from algotrade.core.model.errors import ConfigurationError
from algotrade.data.events import NO_INSTRUMENT_ROWS
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


def test_the_history_copy_holds_only_events_tables_that_store_instrument_ids() -> None:
    # an all-time read of one name opens one file per day; a CIK-keyed table has no id
    copied = load_nightly(FileConfigStore(REPO_ROOT / "config", local=False)).history_copy
    assert copied.event_tables, "events/fund_nav alone is 5,737 day partitions"
    for table in copied.event_tables:
        assert table.startswith("events/") and spec_for(table) is not None, table
        assert table not in NO_INSTRUMENT_ROWS, f"{table} stores no instrument_id"


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
    # ADR 0078: the history copy signs the index (size and content digest), so a swap would void it;
    # a snapshot table keeps one run, so there is nothing to merge
    nightly = load_nightly(FileConfigStore(REPO_ROOT / "config", local=False))
    copied = nightly.history_copy
    assert nightly.compaction.tables == ("outcomes/instrument/forward_returns@v2",)
    for table in nightly.compaction.tables:
        assert spec_for(table).runs == "merge", f"{table} is not a merge-mode table"
        assert table not in copied.instrument_tables, f"{table} has a history copy declared"
        assert not (copied.market_prefix and table.startswith(copied.market_prefix)), table


def test_compaction_never_lists_a_table_whose_runs_are_each_a_groups_whole_result() -> None:
    # ADR 0078 keeps only the changed rows, so a compacted newest run is a delta: the newest-run
    # read (``read_latest_runs``, ADR 0029 amendment) would then return a fraction of a screen
    nightly = load_nightly(FileConfigStore(REPO_ROOT / "config", local=False))
    for table in nightly.compaction.tables:
        assert not spec_for(table).whole_per_group, f"{table} is read by its newest run alone"


def test_release_reads_are_on_by_default_and_the_kill_switch_parses() -> None:
    # ADR 0077 decision 23: the API serves the listed operations from the current serving release
    assert NightlySettings.from_document({}).release_reads is True
    off = NightlySettings.from_document({"serving": {"release_reads": False}})
    assert off.release_reads is False
    with pytest.raises(ConfigurationError, match="serving"):
        NightlySettings.from_document({"serving": {"release_read": False}})
    assert load_nightly(FileConfigStore(REPO_ROOT / "config", local=False)).release_reads is True
