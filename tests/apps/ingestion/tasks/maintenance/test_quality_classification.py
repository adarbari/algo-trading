"""The acceptance check ``reference_classification`` (ADR 0045): FAIL when the vendor's
security types and our name rules disagree on more ACTIVE rows than ``max_type_disagreement``.

The acceptance check of ``market-rollups`` (ADR 0047): every market group has its one
``MKT:US`` row for the session; nothing declared passes.
"""

from datetime import date

import pandas as pd
import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.data import StoreReader
from algotrade.features.site import site_features
from algotrade.services.features import site_features as default_features
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.derived.market_rollups import compute_market_rollups
from algotrade_ingestion.tasks.derived.rollups import SITE
from algotrade_ingestion.tasks.maintenance.quality import (
    check_market_rollups,
    check_reference_classification,
    check_rollup_inputs,
)
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.rollup_store import (
    MARKET_COUNTS,
    market_store,
    only_market_counts,
    store,
    without_market_groups,
)
from tests.helpers.stored_frames import stamped

D = date(2026, 10, 2)
OPERATING = ("Acme Corp. - Common Stock", "COMMON_STOCK", "vendor")
PREFERRED = ("Adamas Trust, Inc. - Series F Preferred Stock", "PREFERRED", "name_over_vendor")
CEF = ("Pimco Income Opportunity Fund", "CEF", "vendor")  # the vendor's type stands


def reader_with(rows: list[tuple[str, str, str]]) -> StoreReader:
    frame = pd.DataFrame(
        [
            {
                "instrument_id": f"EQ:S{i}",
                "symbol": f"S{i}",
                "name": name,
                "is_etf": False,
                "asset_class": "EQUITY",
                "multiplier": 1.0,
                "status": "ACTIVE",
                "security_type": kind,
                "security_type_source": source,
            }
            for i, (name, kind, source) in enumerate(rows)
        ]
    )
    backend = MemoryBackend()
    StoreWriter(backend).write_table("instruments/reference", D, "r", stamped(frame, D, "r"))
    return StoreReader(backend)


def check(rows: list[tuple[str, str, str]], **quality: float) -> tuple[str, dict[str, int]]:
    settings = SourcesSettings.from_document({"quality": quality})
    [result] = check_reference_classification(reader_with(rows), D, settings)
    return result.status, result.data


def test_few_disagreements_pass() -> None:
    status, data = check([OPERATING] * 95 + [PREFERRED] * 2 + [CEF] * 3)
    assert status == "PASS"
    assert (data["name_over_vendor"], data["disagreements"]) == (2, 5)


def test_too_many_disagreements_fail() -> None:
    assert check([OPERATING] * 80 + [PREFERRED] * 20)[0] == "FAIL"  # 20% > 10%
    assert check([OPERATING] * 90 + [CEF] * 10, max_type_disagreement=0.05)[0] == "FAIL"


def test_a_vendor_type_that_the_name_rules_agree_with_is_no_disagreement() -> None:
    agreed = ("Acme Corp. Warrants", "WARRANT", "vendor")
    assert check([OPERATING] * 9 + [agreed])[1]["disagreements"] == 0


def test_no_reference_snapshot_fails() -> None:
    [result] = check_reference_classification(
        StoreReader(MemoryBackend()), D, SourcesSettings.from_document({})
    )
    assert result.status == "FAIL"


def test_too_many_rows_typed_by_the_name_fail_on_their_own_limit() -> None:
    rows = [OPERATING] * 96 + [PREFERRED] * 4  # 4% > 2%, but only 4% disagree (< 10%)
    assert check(rows)[0] == "FAIL"
    assert check(rows, max_name_over_vendor=0.05)[0] == "PASS"


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


def test_a_group_without_input_warns_once_and_never_fails() -> None:
    stats = {
        "ibkr_iv@v1": {"no_input": 2, "no_input_sessions": ["2026-10-05"], "rows": 0},
        "iv30@v1": {"no_input": 0, "no_input_sessions": [], "rows": 9},
    }
    [check] = check_rollup_inputs(stats, date(2026, 10, 6))
    assert (check.name, check.status) == ("rollup_input", "WARN")
    assert check.detail == "ibkr_iv@v1: no input for 2 session(s) (2026-10-05)"
    assert check.data == {"group": "ibkr_iv@v1", "no_input": 2}


def test_rollup_inputs_ignore_clean_groups_and_non_group_keys() -> None:
    stats = {"iv30@v1": {"no_input": 0}, "failed": ["x"], "range": "a..b", "partial": [], "n": 3}
    assert check_rollup_inputs(stats, date(2026, 10, 6)) == []
