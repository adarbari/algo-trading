"""The nightly's site config (``algotrade.config.site.nightly``): its history copy covers what the
Explore history reads."""

import tomllib

import pytest

from algotrade.config.site.settings import NightlySettings, load_nightly
from algotrade.core.model.errors import ConfigurationError
from algotrade.features.registry import GROUPS
from algotrade.storage.configs.files import FileConfigStore
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
