"""The acceptance check of ``market-rollups`` (ADR 0047): every market group has its one
``MKT:US`` row for the session; nothing declared passes."""

import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.features.site import site_features
from algotrade.services.features import site_features as default_features
from algotrade_ingestion.tasks.derived.market_rollups import compute_market_rollups
from algotrade_ingestion.tasks.derived.rollups import SITE
from algotrade_ingestion.tasks.maintenance.quality import check_market_rollups
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.rollup_store import (
    MARKET_COUNTS,
    market_store,
    only_market_counts,
    store,
    without_market_groups,
)

SETTINGS = SourcesSettings()


def test_no_market_group_declared_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    without_market_groups(monkeypatch, site_features(SITE), default_features())
    _, reader = store()
    [check] = check_market_rollups(reader, market_store()[2][-1], SETTINGS)
    assert check.status == "PASS" and "0 market groups" in check.detail


def test_a_row_per_group_for_the_session_passes_and_a_missing_one_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # the task reads the site through its own store, the check through the default one
    only_market_counts(monkeypatch, site_features(SITE), default_features())
    writer, reader, days = market_store()
    [before] = check_market_rollups(reader, days[-1], SETTINGS)
    assert before.status == "FAIL"
    assert before.detail == f"no MKT:US row for {days[-1]}: {MARKET_COUNTS.key}"
    compute_market_rollups(task_ctx(writer), days[-2])
    assert check_market_rollups(reader, days[-1], SETTINGS)[0].status == "FAIL"  # not this day
    compute_market_rollups(task_ctx(writer), days[-1])
    [after] = check_market_rollups(reader, days[-1], SETTINGS)
    assert after.status == "PASS" and "1 market groups" in after.detail
