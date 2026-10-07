"""The ``filings`` step's acceptance (``check_filings``): FAIL above
``[quality] max_filings_failed`` of the CIKs failing (a CIK SEC has no filings for is not a
failure), FAIL when no scoped name has a CIK, WARN when no name resolved, nothing without a run."""

from datetime import date

from algotrade.config.site.settings import SourcesSettings
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import start_run
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.events.filings import TASK
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.maintenance.quality import check_filings
from tests.helpers.ingest_fakes import FIXED, task_ctx

S = date(2026, 10, 5)


def ctx_with(stats: dict[str, int] | None, session: date = S, **settings: float) -> TaskContext:
    ctx = task_ctx(StoreWriter(MemoryBackend()), settings=SourcesSettings(**settings))
    ctx.configs = MemoryConfigStore({})
    if stats is not None:
        record = start_run(TASK, session, FIXED)
        ctx.writer.save_run(record.finish(FIXED, stats=stats))
    return ctx


def test_a_few_failed_ciks_pass_and_too_many_fail() -> None:
    [ok] = check_filings(ctx_with({"names": 100, "ciks": 100, "ciks_failed": 5}), S)
    assert ok.name == "filings_fetched" and ok.status == "PASS"
    assert "5 of 100 CIKs" in ok.detail
    [bad] = check_filings(ctx_with({"names": 100, "ciks": 100, "ciks_failed": 6}), S)
    assert bad.status == "FAIL"


def test_the_threshold_is_the_setting() -> None:
    stats = {"names": 10, "ciks": 10, "ciks_failed": 3}
    assert check_filings(ctx_with(stats, max_filings_failed=0.3), S)[0].status == "PASS"
    assert check_filings(ctx_with(stats, max_filings_failed=0.2), S)[0].status == "FAIL"


def test_names_without_any_cik_fail_and_no_names_warn() -> None:
    [none] = check_filings(ctx_with({"names": 12, "ciks": 0, "ciks_failed": 0}), S)
    assert none.status == "FAIL" and "12 scoped names" in none.detail
    [empty] = check_filings(ctx_with({"names": 0, "ciks": 0, "ciks_failed": 0}), S)
    assert empty.status == "WARN"


def test_only_a_finished_run_of_the_session_is_graded() -> None:
    assert check_filings(ctx_with(None), S) == []  # the step itself fails when its task failed
    other_day = ctx_with({"names": 1, "ciks": 1, "ciks_failed": 1}, session=date(2026, 10, 2))
    assert check_filings(other_day, S) == []


def test_nothing_is_graded_without_a_config_store() -> None:
    ctx = ctx_with({"names": 1, "ciks": 1, "ciks_failed": 1})
    ctx.configs = None
    assert check_filings(ctx, S) == []
