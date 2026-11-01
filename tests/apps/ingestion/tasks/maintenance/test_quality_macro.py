"""The macro step's acceptance (``check_macro``): FAIL when over ``max_macro_stale_share`` of
the enabled series have no observation newer than cadence + lag + 2 days, WARN on any fewer,
FAIL when a series holds fewer vintages than an earlier macro run recorded.

The ``macro-calendar`` step's acceptance (``check_macro_calendar``): FAIL naming the FRED
releases with fewer scheduled dates after the session than ``[quality] min_calendar_future_dates``,
a release the latest run skipped is not graded, nothing without FRED releases.

The ``vx-futures`` step's acceptance (``check_vx_futures``), WARN-only: PASS when a row at or after
the session before is stored, WARN when older, no contract was found or a file failed."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.config.site.events.releases import FOLDER, NAME, MacroReleases
from algotrade.config.site.macro import MacroSettings
from algotrade.config.site.settings import SourcesSettings
from algotrade.data import StoreReader
from algotrade.data.macro.vintages import lagged_vintages
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import RunStatus, start_run
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.macro.calendar import TABLE, ingest_macro_calendar, release_rows
from algotrade_ingestion.tasks.maintenance.quality import (
    VX_TASK,
    check_macro,
    check_macro_calendar,
    check_vx_futures,
    macro_checks,
)
from tests.apps.ingestion.tasks.macro.test_calendar import (
    CPI,
    FOMC,
    Feed,
    context,
    entry,
    rule,
)
from tests.helpers.ingest_fakes import FIXED, task_ctx
from tests.helpers.stored_frames import stamped

D = date(2026, 10, 5)
DAILY = {"cadence": "daily", "release_lag_days": 1}  # stale after 1 + 1 + 3 = 5 days


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
        ([0, 1, 5, 3, 0], "PASS"),  # 5 days is the edge: not stale
        ([0, 1, 6, 3, 0], "WARN"),  # one of five (20%) is not above 20%: a warning
        ([0, 1, 6, 7, 0], "FAIL"),  # two of five
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


BLOCK = {
    "defaults": {
        "source": "published", "kind": "macro", "cadence": "monthly", "pit": "lag",
        "release_lag_days": 70, "revised": True, "licence": "personal", "terms": "t",
        "parser": "french_zip", "date_column": "date",
    },
    "file": [{"prefix": "FF3", "url": "https://x.test/f.zip", "columns": ["SMB", "HML"]}],
}  # fmt: skip


def french_store(macro: MacroSettings, file_ends: date) -> StoreReader:
    """The research series as stored: daily rows ending ``file_ends``, each vintaged +70 days."""
    obs = pd.DataFrame({"obs_date": pd.date_range(end=file_ends, periods=300)})
    rows = []
    for x in macro.series:
        lagged = lagged_vintages(obs, 70).assign(
            instrument_id=x.instrument_id, series=x.key, value=1.0
        )
        rows += lagged.to_dict("records")
    backend = MemoryBackend()
    StoreWriter(backend).write_table("macro/series", D, "m", stamped(rows, D, "m"))
    return StoreReader(backend)


def record_fetch(reader: StoreReader, keys: list[str], session: date = D) -> None:
    run = start_run("macro", session, datetime(2026, 10, 5, 22, tzinfo=UTC))
    run.status, run.stats = RunStatus.COMPLETE, {"vintages": {}, "skipped_series": {}}
    run.items = dict.fromkeys(keys, "OK: 5 rows")
    StoreWriter(reader._backend).save_run(run)


def test_a_french_file_a_month_behind_is_not_stale() -> None:
    """ADR 0087: French's daily files end about a month before the session and each day is known
    from observation + 70 days (``lagged``), so the newest value a session knows is 70 days old,
    and the pull every 28 days lets that drift to about 90: inside the monthly 103-day window.
    A ``daily`` series (stale after 74 days) would flag the 95-day case."""
    macro = MacroSettings.from_documents({}, [BLOCK])
    assert {s.stale_after_days for s in macro.series} == {103}
    keys = [s.key for s in macro.series]
    for file_ends, status in (
        (D - timedelta(days=32), "PASS"), (D - timedelta(days=95), "PASS"),
        (D - timedelta(days=120), "WARN"),
    ):  # fmt: skip
        reader = french_store(macro, file_ends)
        record_fetch(reader, keys)
        checks = by_name(macro_checks(reader, D, SourcesSettings(), macro))
        assert checks["macro_research_fresh"][0] == status, (file_ends, checks)


def test_research_series_are_graded_only_on_a_night_they_were_fetched() -> None:
    macro = MacroSettings.from_documents({}, [BLOCK])
    reader = french_store(macro, D - timedelta(days=200))  # long stale
    status, detail = by_name(macro_checks(reader, D, SourcesSettings(), macro))[
        "macro_research_fresh"
    ]
    assert status == "PASS" and "not graded" in detail and "no macro run" in detail
    record_fetch(reader, [], session=D - timedelta(days=1))  # a fetch of another night
    assert (
        "not graded"
        in by_name(macro_checks(reader, D, SourcesSettings(), macro))["macro_research_fresh"][1]
    )
    record_fetch(reader, ["FF3_SMB"])  # one fetched tonight: only it is graded
    status, detail = by_name(macro_checks(reader, D, SourcesSettings(), macro))[
        "macro_research_fresh"
    ]
    assert status == "WARN" and "1 of 1 fetched" in detail and "FF3_SMB" in detail


def test_research_series_lose_no_vintages_on_the_nights_they_are_graded() -> None:
    macro = MacroSettings.from_documents({}, [BLOCK])
    reader = french_store(macro, D - timedelta(days=32))  # 300 vintages each
    record_run(reader, {"FF3_SMB": 301}, RunStatus.COMPLETE)  # a run once held one more
    quiet = by_name(macro_checks(reader, D, SourcesSettings(), macro))
    assert "macro_vintages" in quiet and quiet["macro_vintages"][0] == "PASS"  # not read tonight
    record_fetch(reader, ["FF3_SMB", "FF3_HML"])
    checks = by_name(macro_checks(reader, D, SourcesSettings(), macro))
    assert (
        checks["macro_vintages"][0] == "FAIL"
        and "FF3_SMB (300 < 301)" in checks["macro_vintages"][1]
    )


def test_research_series_stay_out_of_the_stale_share_and_are_read_without_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys = [f"S{i}" for i in range(5)]
    research = MacroSettings.from_documents({}, [BLOCK])
    both = MacroSettings(registry(*keys).series + research.series)
    reader = store({k: D - timedelta(days=1) for k in keys})
    asked: list[tuple[Any, Any]] = []
    original = StoreReader.table_range

    def spy(
        self: StoreReader, table: str, start: date, end: date, as_of: Any = None,
        instruments: Any = None, columns: Any = None, **rest: Any,
    ) -> Any:  # fmt: skip
        asked.append((instruments, columns))
        return original(self, table, start, end, as_of, instruments, columns, **rest)

    monkeypatch.setattr(StoreReader, "table_range", spy)
    record_fetch(reader, [x.key for x in research.series])
    checks = by_name(macro_checks(reader, D, SourcesSettings(), both))
    assert checks["macro_fresh"][0] == "PASS" and "0 of 5" in checks["macro_fresh"][1]
    assert checks["macro_research_fresh"][0] == "WARN"  # nothing stored for them: stale
    full = [list(i) for i, c in asked if c is None]
    assert full == [[f"MACRO:{k}" for k in keys]]  # the regular series, every column
    lite = [(list(i), set(c)) for i, c in asked if c is not None]
    assert lite == [
        (
            [x.instrument_id for x in research.series],
            {"instrument_id", "obs_date", "vintage_date", "knowledge_ts"},
        )
    ]  # fmt: skip: the research series, the key columns only


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


def test_a_lag_zero_daily_series_survives_a_monday_holiday() -> None:
    """A close dated Friday is 4 days old on the Tuesday after a Monday holiday."""
    tuesday = date(2026, 10, 6)
    reader = store({"A": tuesday - timedelta(days=4)})
    entry = {"cadence": "daily", "release_lag_days": 0}
    one = MacroSettings.from_document(
        {
            "series": [
                {"key": "A", "source": "fred", "kind": "macro", "pit": "lag", "terms": "t", **entry}
            ]
        }
    )
    assert (
        by_name(macro_checks(reader, tuesday, SourcesSettings(), one))["macro_fresh"][0] == "PASS"
    )
    assert one.series[0].stale_after_days == 4 and registry("A").series[0].stale_after_days == 5


def test_check_macro_grades_the_registry_the_run_was_given() -> None:
    """``ctx.configs`` (not a config directory on disk) says which series there are."""
    doc = {"series": [{"key": "ONLY", "source": "fred", "kind": "macro", "cadence": "daily",
                       "pit": "lag", "terms": "t"}]}  # fmt: skip
    ctx = task_ctx(StoreWriter(MemoryBackend()))
    ctx.configs = MemoryConfigStore({("site", "settings", "macro"): doc})
    status, detail = by_name(check_macro(ctx, D))["macro_fresh"]
    assert status == "FAIL" and "1 of 1 series stale" in detail and "ONLY" in detail
    ctx.configs = None
    assert check_macro(ctx, D) == []


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


CAL_SESSION = date(2026, 10, 6)
CAL_DOCUMENT: dict[str, Any] = {
    "release": [
        entry("CPI"),
        entry("FOMC", release_id=101, time_et="14:00"),
        rule("ISM_MFG", 1),
    ]
}


def with_configs(ctx: TaskContext, document: dict[str, Any] | None = CAL_DOCUMENT) -> TaskContext:
    ctx.configs = MemoryConfigStore({("site", FOLDER, NAME): document} if document else {})
    return ctx


def calendar_store(days: dict[str, list[date]]) -> TaskContext:
    """A context over a store holding the given dates of each release, stored on CAL_SESSION."""
    ctx = with_configs(task_ctx(StoreWriter(MemoryBackend())))
    specs = {"CPI": CPI, "FOMC": FOMC}
    for run, (key, dates) in enumerate(days.items()):
        rows = release_rows(specs[key], dates, CAL_SESSION)
        rows = rows.assign(
            session_date=CAL_SESSION,
            knowledge_ts=rows["ts"].iloc[0],
            source="fred",
            run_id=f"r{run}",
        )
        ctx.writer.write_table(TABLE, CAL_SESSION, f"r{run}", rows)
    return ctx


def test_every_fred_release_listing_a_future_date_passes() -> None:
    ctx = calendar_store(
        {"CPI": [date(2026, 10, 14)], "FOMC": [date(2026, 10, 28), date(2026, 12, 9)]}
    )
    [check] = check_macro_calendar(ctx, CAL_SESSION)
    assert check.name == "macro_calendar_future" and check.status == "PASS"
    assert "2 FRED releases" in check.detail


def test_a_release_with_only_past_dates_fails_by_name() -> None:
    ctx = calendar_store({"CPI": [date(2026, 9, 11)], "FOMC": [date(2026, 10, 28)]})
    [check] = check_macro_calendar(ctx, CAL_SESSION)
    assert check.status == "FAIL" and "CPI" in check.detail and "FOMC" not in check.detail


def test_a_release_never_stored_fails() -> None:
    [check] = check_macro_calendar(calendar_store({"FOMC": [date(2026, 10, 28)]}), CAL_SESSION)
    assert check.status == "FAIL" and "CPI" in check.detail


def test_the_threshold_is_the_setting() -> None:
    ctx = calendar_store({"CPI": [date(2026, 10, 14)], "FOMC": [date(2026, 10, 28)]})
    assert check_macro_calendar(ctx, CAL_SESSION)[0].status == "PASS"  # one date each: the default
    ctx.settings = SourcesSettings(min_calendar_future_dates=2)
    assert "CPI, FOMC" in check_macro_calendar(ctx, CAL_SESSION)[0].detail


def test_a_date_stored_after_the_session_is_not_known_by_it() -> None:
    ctx = calendar_store({"CPI": [date(2026, 10, 14)], "FOMC": [date(2026, 10, 28)]})
    [check] = check_macro_calendar(ctx, date(2026, 10, 5))  # both rows were stored on 10-06
    assert check.status == "FAIL"


def test_releases_the_latest_run_skipped_are_not_graded() -> None:
    registry = {"release": [entry("CPI"), entry("FOMC", release_id=101), rule("ISM_MFG", 1)]}
    ctx = with_configs(context(Feed(), fred=False), registry)
    ingest_macro_calendar(
        ctx, MacroReleases.from_document(registry), CAL_SESSION
    )  # no key: all skipped
    [check] = check_macro_calendar(ctx, CAL_SESSION)
    assert check.status == "WARN" and "no FRED release was fetchable" in check.detail


def test_nothing_to_grade_without_configs_or_fred_releases() -> None:
    assert check_macro_calendar(task_ctx(StoreWriter(MemoryBackend())), CAL_SESSION) == []
    only_rules = {"release": [CAL_DOCUMENT["release"][2]]}
    assert check_macro_calendar(with_configs(calendar_store({}), only_rules), CAL_SESSION) == []
    assert check_macro_calendar(with_configs(calendar_store({}), None), CAL_SESSION) == []


def test_a_moved_date_does_not_count_as_a_scheduled_one() -> None:
    ctx = calendar_store({"CPI": [date(2026, 10, 14)], "FOMC": [date(2026, 10, 28)]})
    rows = release_rows(CPI, [date(2026, 10, 14)], CAL_SESSION).assign(
        status="moved", known_from=CAL_SESSION, session_date=CAL_SESSION, source="fred", run_id="r9"
    )
    ctx.writer.write_table(
        TABLE,
        CAL_SESSION,
        "r9",
        rows.assign(knowledge_ts=rows["ts"].iloc[0] + pd.Timedelta(days=1)),
    )
    [check] = check_macro_calendar(ctx, CAL_SESSION)
    assert check.status == "FAIL" and "CPI" in check.detail  # its only future date moved


# --- the vx-futures step's acceptance (``check_vx_futures``, WARN-only, EB D3)
VX_FRIDAY = date(2026, 10, 16)  # the session before is Thursday 10-15


def vx_ctx(stats: dict[str, object] | None, session: date = VX_FRIDAY) -> TaskContext:
    ctx = task_ctx(StoreWriter(MemoryBackend()))
    if stats is not None:
        ctx.writer.save_run(start_run(VX_TASK, session, FIXED).finish(FIXED, stats=stats))
    return ctx


def test_the_session_before_is_enough_since_the_session_itself_is_published_next_morning() -> None:
    [check] = check_vx_futures(vx_ctx({"latest": "2026-10-15", "listed": 20}), VX_FRIDAY)
    assert check.name == "vx_futures_fresh" and check.status == "PASS"
    assert (
        check_vx_futures(vx_ctx({"latest": "2026-10-16", "listed": 20}), VX_FRIDAY)[0].status
        == "PASS"
    )


def test_older_data_no_contract_and_fetch_errors_warn_and_never_fail() -> None:
    [stale] = check_vx_futures(vx_ctx({"latest": "2026-10-13", "listed": 20}), VX_FRIDAY)
    assert stale.status == "WARN" and "2026-10-13" in stale.detail and "2026-10-15" in stale.detail
    assert check_vx_futures(vx_ctx({"latest": None, "listed": 20}), VX_FRIDAY)[0].status == "WARN"
    none_listed = check_vx_futures(vx_ctx({"latest": "2026-10-15", "listed": 0}), VX_FRIDAY)[0]
    assert none_listed.status == "WARN" and "no VX contract" in none_listed.detail
    errors = {"latest": "2026-10-15", "listed": 20, "items": {"FETCH_ERROR": 3, "OK": 20}}
    failed = check_vx_futures(vx_ctx(errors), VX_FRIDAY)[0]
    assert failed.status == "WARN" and "3 expiry files" in failed.detail


def test_nothing_without_a_run_of_the_session() -> None:
    assert check_vx_futures(vx_ctx(None), VX_FRIDAY) == []
    other = vx_ctx({"latest": "2026-10-15", "listed": 20}, session=date(2026, 10, 15))
    assert check_vx_futures(other, VX_FRIDAY) == []


def test_nothing_without_a_vx_run_of_the_session() -> None:
    assert check_vx_futures(vx_ctx(None), VX_FRIDAY) == []
    other = vx_ctx({"latest": "2026-10-15", "listed": 20}, session=date(2026, 10, 15))
    assert check_vx_futures(other, VX_FRIDAY) == []
