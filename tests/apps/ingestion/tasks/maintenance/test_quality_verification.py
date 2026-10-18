"""The IBKR quality checks. ``futures_roots_served``: WARN (never FAIL) when a configured
futures root stored no priced curve; nothing while ``[ibkr]`` is disabled or nothing was
written. ``verification``: graded rows of ``verification/ibkr`` for the
session; FAIL above ``max_verify_failures`` failing, WARN on any FAIL or on no rows while
``[ibkr]`` is enabled, nothing at all while it is disabled (the default). ``ibkr_vols_in_range``:
FAIL above ``max_ibkr_vol_rejected`` of the session's ``volatility/ibkr_iv30`` rows with a
vol nulled for being out of bounds (zero, or an IV above 5), WARN on any."""

from datetime import date

import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.maintenance.quality import (
    check_futures_curves,
    check_ibkr_vols,
    check_verification,
)
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


def reader_with_vols(rejects: list[str | None]) -> StoreReader:
    backend = MemoryBackend()
    rows = [
        {"instrument_id": f"EQ:S{i}", "symbol": f"S{i}", "iv30_ibkr": None if r else 0.3,
         "hv30_ibkr": 0.2, "source_kind": "snapshot", "vol_reject": r}
        for i, r in enumerate(rejects)
    ]  # fmt: skip
    if rows:
        frame = stamped(rows, D, "v")
        StoreWriter(backend).write_table("volatility/ibkr_iv30", D, "v", frame)
    return StoreReader(backend)


@pytest.mark.parametrize(
    ("rejects", "expected"),
    [
        ([None] * 100, "PASS"),
        ([None] * 99 + ["iv30_ibkr 9.07 outside (0, 5]"], "WARN"),  # 1%: any warns
        ([None] * 9 + ["iv30_ibkr 1975.65 outside (0, 5]"], "FAIL"),  # 10% > 2%
    ],
)
def test_ibkr_vols_check(rejects: list[str | None], expected: str) -> None:
    [check] = check_ibkr_vols(reader_with_vols(rejects), D, ON)
    assert check.status == expected
    if expected != "PASS":
        assert "e.g. S" in check.detail


def test_ibkr_vols_check_is_silent_when_disabled_or_nothing_written() -> None:
    assert check_ibkr_vols(reader_with_vols(["x"]), D, SourcesSettings()) == []
    assert check_ibkr_vols(reader_with_vols([]), D, ON) == []


FUTURES = SourcesSettings.from_document(
    {"ibkr": {"enabled": True, "futures_roots": ["CL:NYMEX", "NG:NYMEX"]}}
)


def reader_with_curves(roots: dict[str, float | None]) -> StoreReader:
    backend = MemoryBackend()
    rows = [
        {"instrument_id": f"FUT:{r}:2026-11", "ts": D, "parent_id": f"FUT:{r}", "root": r,
         "contract_month": "2026-11", "price": p}
        for r, p in roots.items()
    ]  # fmt: skip
    if rows:
        StoreWriter(backend).write_table("rates/futures_curve", D, "c", stamped(rows, D, "c"))
    return StoreReader(backend)


@pytest.mark.parametrize(
    ("served", "expected"),
    [({"CL": 70.0, "NG": 3.0}, "PASS"), ({"CL": 70.0, "NG": None}, "WARN")],
)
def test_futures_roots_served(served: dict[str, float | None], expected: str) -> None:
    [check] = check_futures_curves(reader_with_curves(served), D, FUTURES)
    assert check.status == expected and "of 2 futures roots" in check.detail
    assert ("none for NG" in check.detail) == (expected == "WARN")


def test_futures_check_is_silent_when_off_unconfigured_or_empty() -> None:
    assert check_futures_curves(reader_with_curves({}), D, FUTURES) == []  # step skipped
    assert check_futures_curves(reader_with_curves({"CL": 1.0}), D, SourcesSettings()) == []
    assert check_futures_curves(reader_with_curves({"CL": 1.0}), D, ON) == []  # no roots
