"""``analyst-probe``: one request per endpoint, a verdict per (vendor, endpoint) in
``analyst/vendor_access``, FMP's calls counted against ``[fmp] daily_budget``."""

from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from itertools import count

import pandas as pd
import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.schemas import validate_frame
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.analyst.budget import fmp_calls_today
from algotrade_ingestion.tasks.analyst.probe import TABLE, run
from algotrade_ingestion.tasks.framework.registry import TASKS
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_sources.framework.http import HttpError
from algotrade_sources.vendors.finnhub.probe import FinnhubProbe
from algotrade_sources.vendors.fmp.probe import FmpProbe
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for, task_ctx

DAY = date(2026, 10, 16)
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "sources"
ROWS = (FIXTURES / "fmp" / "price_target_consensus_aapl.json").read_bytes()
FMP_402 = (FIXTURES / "fmp" / "premium_402.txt").read_bytes()
FINNHUB_403 = (FIXTURES / "finnhub" / "price_target_403.json").read_bytes()

type Answers = dict[str, bytes | int]  # endpoint path fragment -> payload, or an error status


def transport(answers: Answers, calls: list[str]) -> Callable[[str], bytes]:
    def get(url: str) -> bytes:
        calls.append(url)
        for fragment, answer in answers.items():
            if fragment in url:
                if isinstance(answer, int):
                    raise HttpError(answer, body=FMP_402)
                return answer
        raise AssertionError(f"unexpected request {url}")

    return get


FMP_ANSWERS: Answers = {
    "/quote?": ROWS,
    "period=annual": ROWS,
    "period=quarter": 402,
    "price-target-consensus": ROWS,
    "grades-consensus": b"[]",  # empty for a covered large-cap: LIMITED
    "/grades?": 429,
}
FINNHUB_ANSWERS: Answers = {"stock/recommendation": ROWS, "stock/price-target": 403}


def clock() -> Callable[[], datetime]:
    ticks: Iterator[int] = count()
    return lambda: datetime(2026, 10, 16, 9, tzinfo=UTC) + timedelta(minutes=next(ticks))


def context(
    writer: StoreWriter | None = None,
    fmp: Answers | None = FMP_ANSWERS,
    finnhub: Answers | None = FINNHUB_ANSWERS,
    budget: int = 200,
    fmp_calls: list[str] | None = None,
    now: Callable[[], datetime] | None = None,
) -> TaskContext:
    sources = {}
    if fmp is not None:
        sources["fmp_probe"] = FmpProbe(
            http_for(transport(fmp, [] if fmp_calls is None else fmp_calls))
        )
    if finnhub is not None:
        sources["finnhub_probe"] = FinnhubProbe(http_for(transport(finnhub, [])))
    ctx = task_ctx(
        writer or StoreWriter(MemoryBackend()),
        clock=now or clock(),
        sources=sources,
        settings=SourcesSettings(fmp_daily_budget=budget),
    )
    ctx.unavailable = {
        "fmp_probe": "ALGOTRADE_FMP_API_KEY is not set: add it to .env",
        "finnhub_probe": "ALGOTRADE_FINNHUB_API_KEY is not set: add it to .env",
    }
    return ctx


def stored(ctx: TaskContext) -> pd.DataFrame:
    frame = ctx.reader.table(TABLE, DAY)
    assert frame is not None
    return frame.set_index(["source", "endpoint"]).sort_index()


def test_each_endpoint_is_classified_allowed_denied_or_limited_and_stored() -> None:
    ctx = context()
    record = run(ctx, {"session": DAY})
    assert record.status is RunStatus.COMPLETE
    got = stored(ctx)
    assert {k: (r["status"], r["http_code"]) for k, r in got.iterrows()} == {
        ("finnhub", "price_target"): ("DENIED", 403),
        ("finnhub", "recommendation"): ("ALLOWED", 200),
        ("fmp", "estimates_annual"): ("ALLOWED", 200),
        ("fmp", "estimates_quarter"): ("DENIED", 402),  # the free plan's premium period
        ("fmp", "grades"): ("LIMITED", 429),
        ("fmp", "price_targets"): ("ALLOWED", 200),
        ("fmp", "quote"): ("ALLOWED", 200),
        ("fmp", "ratings_summary"): ("LIMITED", 200),  # an empty payload for AAPL
    }
    assert (
        got.loc[("fmp", "quote"), "rows"] == 1
        and got.loc[("fmp", "quote"), "checked_ts"].year == 2026
    )
    assert record.stats["licence"] == {"fmp": "personal", "finnhub": "personal"}
    assert record.stats["fmp_calls_today"] == 6 and record.stats["fmp_daily_budget"] == 200
    validate_frame(TABLE, ctx.reader.table(TABLE, DAY))  # type: ignore[arg-type]


def test_a_later_run_replaces_a_verdict_and_keeps_the_vendor_it_did_not_ask() -> None:
    writer, now = StoreWriter(MemoryBackend()), clock()  # one clock: the runs get distinct ids
    run(context(writer, now=now), {"session": DAY})
    flipped = {**FMP_ANSWERS, "period=quarter": ROWS}  # the plan was upgraded
    ctx = context(writer, fmp=flipped, finnhub=None, now=now)  # a run with no Finnhub key
    record = run(ctx, {"session": DAY})
    assert record.status is RunStatus.COMPLETE
    assert record.stats["skipped"] == {"finnhub_probe": ctx.unavailable["finnhub_probe"]}
    got = stored(ctx)
    assert got.loc[("fmp", "estimates_quarter"), "status"] == "ALLOWED"
    assert got.loc[("finnhub", "price_target"), "status"] == "DENIED"  # the earlier run's row
    assert len(got) == 8


def test_no_configured_vendor_fails_the_run_and_writes_nothing() -> None:
    ctx = context(fmp=None, finnhub=None)
    record = run(ctx, {"session": DAY})
    assert record.status is RunStatus.FAILED
    assert "ALGOTRADE_FMP_API_KEY is not set" in str(record.stats["failed_because"])
    assert ctx.reader.table(TABLE, DAY) is None


def test_an_answer_that_is_no_verdict_fails_its_item_and_stores_no_row_for_it() -> None:
    ctx = context(fmp={**FMP_ANSWERS, "/quote?": 503}, finnhub=None)
    record = run(ctx, {"session": DAY})
    assert record.status is RunStatus.PARTIAL
    assert record.items["fmp:quote"].startswith("FETCH_ERROR")
    assert ("fmp", "quote") not in stored(ctx).index  # a verdict of an earlier run stays


def test_the_session_parameter_is_required() -> None:
    with pytest.raises(ValueError, match="session"):
        run(context(), {})


# ------------------------------------------------------------------------------- budget


def spent(writer: StoreWriter, day: date, n: int, status: str = "ALLOWED") -> None:
    started = datetime(day.year, day.month, day.day, 6, tzinfo=UTC)
    record = RunRecord(f"probe-{day}", "analyst-probe", day, started)
    record.status, record.finished_at = RunStatus.FAILED, started  # a failed run spent them too
    record.items = {f"fmp:e{i}": status for i in range(n)}
    writer._backend.runs.save(record)  # type: ignore[attr-defined]


def test_calls_already_spent_today_count_and_yesterdays_do_not() -> None:
    writer = StoreWriter(MemoryBackend())
    spent(writer, DAY, 190)
    spent(writer, DAY - timedelta(days=1), 150)
    ctx = context(writer)
    with IngestRun(ctx, "analyst-probe", DAY) as probe_run:
        assert fmp_calls_today(probe_run) == 190
        probe_run.record_item("fmp:quote", "ALLOWED")
        probe_run.record_item("fmp:grades", "OVER_BUDGET: not made")  # no call was made
        assert fmp_calls_today(probe_run) == 191


def test_endpoints_over_the_daily_budget_are_not_asked_and_the_run_is_partial() -> None:
    writer = StoreWriter(MemoryBackend())
    spent(writer, DAY, 197)  # 3 left of 200
    calls: list[str] = []
    ctx = context(writer, fmp_calls=calls, finnhub=None)
    record = run(ctx, {"session": DAY})
    assert len(calls) == 3  # the first three endpoints only
    assert record.status is RunStatus.PARTIAL
    refused = [k for k, v in record.items.items() if v.startswith("OVER_BUDGET")]
    assert refused == ["fmp:price_targets", "fmp:ratings_summary", "fmp:grades"]
    assert {e for _, e in stored(ctx).index} == {"quote", "estimates_annual", "estimates_quarter"}


def test_finnhub_is_not_counted_against_the_fmp_budget() -> None:
    ctx = context(fmp=None, budget=0)
    record = run(ctx, {"session": DAY})
    assert record.status is RunStatus.COMPLETE and record.stats["fmp_calls_today"] == 0


def test_the_task_is_registered_in_no_workflow_with_its_table_and_optional_sources() -> None:
    task = TASKS["analyst-probe"]
    assert task.tables == (TABLE,) and task.sources == ()
    assert set(task.optional_sources) == {"fmp_probe", "finnhub_probe"}
