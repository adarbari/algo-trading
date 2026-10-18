"""The ``filings`` step's acceptance (``check_filings``): FAIL above
``[quality] max_filings_failed`` of the SEC requests failing (CIKs and daily index days; a CIK
SEC has no filings for is not a failure), FAIL when no name has a CIK, PASS when a quiet night
needed no request, WARN when no name resolved, nothing without a run."""

from datetime import date
from typing import Any

from algotrade.config.site.settings import SourcesSettings
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import start_run
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.events.filings import TASK
from algotrade_ingestion.tasks.events.ipo_lockups import TASK as IPO_LOCKUPS_TASK
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.maintenance.quality import check_filings, check_ipo_lockups
from tests.helpers.ingest_fakes import FIXED, task_ctx

S = date(2026, 10, 5)


def ctx_with(stats: dict[str, int] | None, session: date = S, **settings: float) -> TaskContext:
    ctx = task_ctx(StoreWriter(MemoryBackend()), settings=SourcesSettings(**settings))
    if stats is not None:
        record = start_run(TASK, session, FIXED)
        ctx.writer.save_run(record.finish(FIXED, stats=stats))
    return ctx


def test_a_few_failed_ciks_pass_and_too_many_fail() -> None:
    [ok] = check_filings(ctx_with({"names": 100, "with_cik": 90, "ciks": 100, "ciks_failed": 5}), S)
    assert ok.name == "filings_fetched" and ok.status == "PASS"
    assert "5 of 100 CIKs" in ok.detail
    [bad] = check_filings(
        ctx_with({"names": 100, "with_cik": 90, "ciks": 100, "ciks_failed": 6}), S
    )
    assert bad.status == "FAIL"


def test_the_threshold_is_the_setting() -> None:
    stats = {"names": 10, "with_cik": 10, "ciks": 10, "ciks_failed": 3}
    assert check_filings(ctx_with(stats, max_filings_failed=0.3), S)[0].status == "PASS"
    assert check_filings(ctx_with(stats, max_filings_failed=0.2), S)[0].status == "FAIL"


def test_index_days_count_with_the_ciks() -> None:
    stats = {"names": 50, "with_cik": 50, "ciks": 18, "ciks_failed": 0, "days": 2, "days_failed": 1}
    [one] = check_filings(ctx_with(stats), S)  # 1 of 20 requests is under the limit, but a
    assert one.status == "FAIL" and "1 of 2 index days" in one.detail  # failed day stops the walk
    stats["days_failed"] = 0
    assert check_filings(ctx_with(stats), S)[0].status == "PASS"


def test_names_without_any_cik_fail_and_no_names_warn() -> None:
    none = check_filings(ctx_with({"names": 12, "with_cik": 0, "ciks": 0}), S)[0]
    assert none.status == "FAIL" and "none of 12 names" in none.detail
    assert check_filings(ctx_with({"names": 0}), S)[0].status == "WARN"


def test_a_quiet_night_with_nothing_to_ask_passes() -> None:
    quiet = check_filings(ctx_with({"names": 5000, "with_cik": 4800, "ciks": 0, "days": 0}), S)
    assert quiet[0].status == "PASS"


def test_only_a_finished_run_of_the_session_is_graded() -> None:
    assert check_filings(ctx_with(None), S) == []  # the step itself fails when its task failed
    other = {"names": 1, "with_cik": 1, "ciks": 1, "ciks_failed": 1}
    assert check_filings(ctx_with(other, session=date(2026, 10, 2)), S) == []


def ipo_ctx(items: dict[str, str] | None, session: date = S, **stats: Any) -> TaskContext:
    ctx = task_ctx(StoreWriter(MemoryBackend()))
    if items is not None:
        record = start_run(IPO_LOCKUPS_TASK, session, FIXED)
        record.items = items
        ctx.writer.save_run(record.finish(FIXED, stats=stats))
    return ctx


def test_ipo_lockups_a_clean_run_passes_with_its_counts() -> None:
    items = {"win:2026-10": "OK: 4 hits", "acc:a": "OK: EXTRACTED"}
    [check] = check_ipo_lockups(ipo_ctx(items, hits=4, read=1), S)
    assert check.name == "ipo_lockups_fetched" and check.status == "PASS"
    assert check.detail == "4 prospectuses listed, 1 read, 0 failed"


def test_ipo_lockups_a_failed_month_or_prospectus_warns_and_never_fails() -> None:
    items = {"win:2026-09": "FETCH_ERROR: HTTP 500", "acc:a": "FETCH_ERROR: boom", "acc:b": "OK: x"}
    [check] = check_ipo_lockups(ipo_ctx(items, hits=3, read=2), S)
    assert check.status == "WARN" and "win:2026-09" in check.detail and "acc:a" in check.detail


def test_ipo_lockups_nothing_without_a_finished_run_of_the_session() -> None:
    assert check_ipo_lockups(ipo_ctx(None), S) == []
    assert check_ipo_lockups(ipo_ctx({"acc:a": "OK: x"}, session=date(2026, 10, 2)), S) == []
