"""The ``macro-calendar`` step's acceptance (``check_macro_calendar``): FAIL naming the FRED
releases with fewer scheduled dates after the session than ``[quality] min_calendar_future_dates``,
a release the latest run skipped is not graded, nothing without FRED releases."""

from datetime import date
from typing import Any

from algotrade.config.site.events.releases import FOLDER, NAME
from algotrade.config.site.settings import SourcesSettings
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.macro.calendar import TABLE, ingest_macro_calendar, release_rows
from algotrade_ingestion.tasks.maintenance.quality import check_macro_calendar
from tests.apps.ingestion.tasks.macro.test_calendar import (
    CPI,
    FOMC,
    REGISTRY,
    Feed,
    context,
    entry,
    rule,
)
from tests.helpers.ingest_fakes import task_ctx

S = date(2026, 10, 6)
DOCUMENT: dict[str, Any] = {
    "release": [entry("CPI"), entry("FOMC", release_id=101, time_et="14:00"), rule("ISM_MFG", 1)]
}


def with_configs(ctx: TaskContext, document: dict[str, Any] | None = DOCUMENT) -> TaskContext:
    ctx.configs = MemoryConfigStore({("site", FOLDER, NAME): document} if document else {})
    return ctx


def store(days: dict[str, list[date]]) -> TaskContext:
    """A context over a store holding the given dates of each release, stored on ``S``."""
    ctx = with_configs(task_ctx(StoreWriter(MemoryBackend())))
    specs = {"CPI": CPI, "FOMC": FOMC}
    for run, (key, dates) in enumerate(days.items()):
        rows = release_rows(specs[key], dates, S)
        rows = rows.assign(
            session_date=S, knowledge_ts=rows["ts"].iloc[0], source="fred", run_id=f"r{run}"
        )
        ctx.writer.write_table(TABLE, S, f"r{run}", rows)
    return ctx


def test_every_fred_release_listing_a_future_date_passes() -> None:
    ctx = store({"CPI": [date(2026, 10, 14)], "FOMC": [date(2026, 10, 28), date(2026, 12, 9)]})
    [check] = check_macro_calendar(ctx, S)
    assert check.name == "macro_calendar_future" and check.status == "PASS"
    assert "2 FRED releases" in check.detail


def test_a_release_with_only_past_dates_fails_by_name() -> None:
    ctx = store({"CPI": [date(2026, 9, 11)], "FOMC": [date(2026, 10, 28)]})
    [check] = check_macro_calendar(ctx, S)
    assert check.status == "FAIL" and "CPI" in check.detail and "FOMC" not in check.detail


def test_a_release_never_stored_fails() -> None:
    [check] = check_macro_calendar(store({"FOMC": [date(2026, 10, 28)]}), S)
    assert check.status == "FAIL" and "CPI" in check.detail


def test_the_threshold_is_the_setting() -> None:
    ctx = store({"CPI": [date(2026, 10, 14)], "FOMC": [date(2026, 10, 28)]})
    assert check_macro_calendar(ctx, S)[0].status == "PASS"  # one date each: the default
    ctx.settings = SourcesSettings(min_calendar_future_dates=2)
    assert "CPI, FOMC" in check_macro_calendar(ctx, S)[0].detail


def test_a_date_stored_after_the_session_is_not_known_by_it() -> None:
    ctx = store({"CPI": [date(2026, 10, 14)], "FOMC": [date(2026, 10, 28)]})
    [check] = check_macro_calendar(ctx, date(2026, 10, 5))  # both rows were stored on 10-06
    assert check.status == "FAIL"


def test_releases_the_latest_run_skipped_are_not_graded() -> None:
    ctx = with_configs(context(Feed(), fred=False))
    ingest_macro_calendar(ctx, REGISTRY, S)  # every FRED release skipped (no key)
    [check] = check_macro_calendar(ctx, S)
    assert check.status == "WARN" and "no FRED release was fetchable" in check.detail


def test_nothing_to_grade_without_configs_or_fred_releases() -> None:
    assert check_macro_calendar(task_ctx(StoreWriter(MemoryBackend())), S) == []
    only_rules = {"release": [DOCUMENT["release"][2]]}
    assert check_macro_calendar(with_configs(store({}), only_rules), S) == []
    assert check_macro_calendar(with_configs(store({}), None), S) == []
