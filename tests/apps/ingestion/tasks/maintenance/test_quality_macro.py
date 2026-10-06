"""The macro step's acceptance (``check_macro``): FAIL when over ``max_macro_stale_share`` of
the enabled series have no observation newer than cadence + lag + 2 days, WARN on any fewer,
FAIL when a series holds fewer vintages than an earlier macro run recorded."""

from datetime import UTC, date, datetime, timedelta

import pytest

from algotrade.config.site.macro import MacroSettings
from algotrade.config.site.settings import SourcesSettings
from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus, start_run
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.maintenance.quality import check_macro, macro_checks
from tests.helpers.stored_frames import stamped

D = date(2026, 10, 5)
DAILY = {"cadence": "daily", "release_lag_days": 1}  # stale after 1 + 1 + 2 = 4 days


def registry(*keys: str, source: str = "fred") -> MacroSettings:
    return MacroSettings.from_document(
        {
            "series": [
                {"key": k, "source": source, "kind": "macro", "pit": "lag", "terms": "t", **DAILY}
                | ({"url": "https://x.test/f.csv", "date_column": "d", "value_column": "v"}
                   if source == "published" else {})
                for k in keys
            ]
        }
    )  # fmt: skip


def store(newest: dict[str, date], vintages: int = 1) -> StoreReader:
    """Each series with ``vintages`` observations ending at its ``newest`` (vintage = obs)."""
    backend, rows = MemoryBackend(), []
    for key, last in newest.items():
        for i in range(vintages):
            day = last - timedelta(days=i)
            rows.append(
                {"instrument_id": f"MACRO:{key}", "series": key, "obs_date": day,
                 "vintage_date": day, "value": 1.0, "vintage_kind": "lagged"}
            )  # fmt: skip
    if rows:
        StoreWriter(backend).write_table("macro/series", D, "m", stamped(rows, D, "m"))
    return StoreReader(backend)


def by_name(checks: list) -> dict[str, tuple[str, str]]:  # type: ignore[type-arg]
    return {c.name: (c.status, c.detail) for c in checks}


@pytest.mark.parametrize(
    ("ages", "status"),
    [
        ([0, 1, 4, 3, 0], "PASS"),  # 4 days is the edge: not stale
        ([0, 1, 5, 3, 0], "WARN"),  # one of five (20%) is not above 20%: a warning
        ([0, 1, 5, 6, 0], "FAIL"),  # two of five
    ],
)
def test_stale_series_fail_above_the_share(ages: list[int], status: str) -> None:
    keys = [f"S{i}" for i in range(5)]
    reader = store({k: D - timedelta(days=a) for k, a in zip(keys, ages, strict=True)})
    checks = macro_checks(reader, D, SourcesSettings(), registry(*keys))
    fresh = by_name(checks)["macro_fresh"]
    assert fresh[0] == status
    if status != "PASS":
        assert "S2" in fresh[1] and "max 20%" in fresh[1]


def test_a_series_with_no_value_in_the_window_is_stale_and_nothing_stored_fails() -> None:
    checks = macro_checks(store({}), D, SourcesSettings(), registry("A", "B"))
    status, detail = by_name(checks)["macro_fresh"]
    assert status == "FAIL" and "2 of 2 series stale" in detail


def test_only_known_vintages_count() -> None:
    reader = store({"A": D + timedelta(days=3)})  # an observation public after the session
    assert (
        by_name(macro_checks(reader, D, SourcesSettings(), registry("A")))["macro_fresh"][0]
        == "FAIL"
    )


def test_a_disabled_source_is_left_out() -> None:
    off = SourcesSettings.from_document({"fred": {"enabled": False}})
    assert macro_checks(store({}), D, off, registry("A")) == []
    on = SourcesSettings.from_document({"published": {"enabled": True}})
    assert macro_checks(store({}), D, on, registry("A", source="published"))[0].status == "FAIL"


def record_run(
    reader: StoreReader,
    vintages: dict[str, int],
    status: RunStatus,
    minute: int = 0,
    skipped: dict[str, str] | None = None,
) -> None:
    run = start_run("macro", D, datetime(2026, 10, 4, 22, minute, tzinfo=UTC))
    run.status, run.stats = status, {"vintages": vintages, "skipped_series": skipped or {}}
    StoreWriter(reader._backend).save_run(run)


def test_a_series_that_lost_vintages_fails() -> None:
    reader = store({"A": D, "B": D}, vintages=3)
    record_run(reader, {"A": 3, "B": 5}, RunStatus.COMPLETE)
    record_run(reader, {"A": 99}, RunStatus.FAILED, minute=1)  # a failed run recorded nothing real
    checks = macro_checks(reader, D, SourcesSettings(), registry("A", "B"))
    status, detail = by_name(checks)["macro_vintages"]
    assert status == "FAIL" and "B (3 < 5)" in detail and "A (" not in detail


def test_no_lost_vintages_passes_with_the_totals() -> None:
    reader = store({"A": D}, vintages=2)
    record_run(reader, {"A": 2}, RunStatus.PARTIAL)
    status, detail = by_name(macro_checks(reader, D, SourcesSettings(), registry("A")))[
        "macro_vintages"
    ]
    assert status == "PASS" and "2 vintages of 1 series" in detail


def test_check_macro_reads_the_sites_registry() -> None:
    checks = check_macro(store({}), D, SourcesSettings())
    status, detail = by_name(checks)["macro_fresh"]
    assert status == "FAIL" and "series stale" in detail


NO_KEY = "ALGOTRADE_FRED_API_KEY is not set"


def test_series_the_run_skipped_are_not_graded_but_are_named() -> None:
    reader = store({"A": D, "B": D})  # C and D have no data: skipped for want of a key
    record_run(reader, {}, RunStatus.COMPLETE, skipped={"C": NO_KEY, "D": NO_KEY})
    fresh = by_name(macro_checks(reader, D, SourcesSettings(), registry("A", "B", "C", "D")))[
        "macro_fresh"
    ]
    assert fresh[0] == "PASS" and "0 of 2 series stale" in fresh[1]
    assert f"2 skipped, not graded (C, D: {NO_KEY})" in fresh[1]


def test_a_fetched_series_that_is_stale_still_fails_next_to_skipped_ones() -> None:
    reader = store({"A": D - timedelta(days=30)})
    record_run(reader, {}, RunStatus.COMPLETE, skipped={"B": NO_KEY})
    fresh = by_name(macro_checks(reader, D, SourcesSettings(), registry("A", "B")))["macro_fresh"]
    assert fresh[0] == "FAIL" and "1 of 1 series stale" in fresh[1]


def test_when_every_series_was_skipped_the_check_warns_instead_of_failing() -> None:
    reader = store({})
    record_run(reader, {}, RunStatus.COMPLETE, skipped={"A": NO_KEY, "B": NO_KEY})
    checks = macro_checks(reader, D, SourcesSettings(), registry("A", "B"))
    status, detail = by_name(checks)["macro_fresh"]
    assert status == "WARN" and "no macro series was fetchable" in detail and "2 skipped" in detail
    assert by_name(checks)["macro_vintages"][0] == "PASS"
