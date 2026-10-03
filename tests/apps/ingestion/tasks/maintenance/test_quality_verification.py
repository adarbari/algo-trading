"""The quality check ``verification``: graded rows of ``verification/ibkr`` for the session;
FAIL above ``max_verify_failures`` failing, WARN on any FAIL or on no rows while ``[ibkr]``
is enabled, nothing at all while it is disabled (the default)."""

from datetime import date

import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.maintenance.quality import check_verification
from tests.helpers.stored_frames import stamped

D = date(2026, 10, 2)
ON = SourcesSettings.from_document({"ibkr": {"enabled": True}})


def reader_with(statuses: list[str]) -> StoreReader:
    backend = MemoryBackend()
    rows = [
        {"instrument_id": f"EQ:S{i}", "symbol": f"S{i}", "check": "close", "status": s,
         "ours": 1.0, "theirs": 1.0, "diff": 0.0, "tolerance": 0.002, "note": ""}
        for i, s in enumerate(statuses)
    ]  # fmt: skip
    if rows:
        StoreWriter(backend).write_table("verification/ibkr", D, "v", stamped(rows, D, "v"))
    return StoreReader(backend)


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (["PASS"] * 10 + ["NA"] * 5, "PASS"),
        (["PASS"] * 19 + ["FAIL"], "WARN"),  # 5%: any FAIL warns
        (["PASS"] * 8 + ["FAIL"] * 2 + ["NA"] * 10, "FAIL"),  # 20% of graded checks
        ([], "WARN"),  # enabled but nothing verified (gateway down?)
    ],
)
def test_verification_check(statuses: list[str], expected: str) -> None:
    [check] = check_verification(reader_with(statuses), D, ON)
    assert check.status == expected
    if "FAIL" in statuses:
        assert "failing: S" in check.detail


def test_nothing_while_ibkr_is_disabled() -> None:
    assert SourcesSettings().vendor("ibkr").enabled is False  # off unless the owner turns it on
    assert check_verification(reader_with(["FAIL"]), D, SourcesSettings()) == []


def test_threshold_from_sources_toml() -> None:
    lenient = SourcesSettings.from_document(
        {"ibkr": {"enabled": True}, "quality": {"max_verify_failures": 0.5}}
    )
    [check] = check_verification(reader_with(["PASS", "FAIL"]), D, lenient)
    assert check.status == "WARN" and "(max 50%)" in check.detail
