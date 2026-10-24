"""The Admin screener runs: every screen run record of every status for the site and the declared
users, newest first, filtered by owner / screener / status, what each recorded (a run that never
finished has no decisions, never 0), one run by id (never another job's), and its frozen row."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.services.read.ops.admin_runs.screener_runs import (
    load_screener_run,
    load_screener_run_changes,
    load_screener_runs,
)
from algotrade.services.screening.run import run_job_name
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.result_writer import ResultWriter
from tests.unit.services.read.evaluation.conftest import DOCS, stores

DAY = date(2026, 10, 1)
T = datetime(2026, 10, 2, 3, tzinfo=UTC)
DOCS_WITH_MINE: dict[tuple[str, str, str], dict[str, Any]] = {
    **DOCS,
    ("local", "screeners", "mine@1"): {
        "id": "mine", "kind": "screener", "impl": "rules", "version": 1, "selection": "active",
        "criteria": {"price": {"field": "rollup.price_stats@v2.close", "op": "gt", "value": 5}},
    },
}  # fmt: skip
GOOD: dict[str, Any] = {
    "config_id": "momo", "user": "site", "config_hash": "h1", "config_version": 3,
    "summary": {"decisions": {"QUALIFIED": 4, "REJECT": 9, "PAUSED": 2}},
    "regime": {"label": "CALM", "size_multiplier": 1.0, "paused_reason": None},
    "coverage": "PARTIAL", "missing_tables": ["rollups/ibkr_iv"],
    "missing_optional_tables": ["rollups/other"],
}  # fmt: skip


@pytest.fixture
def backend() -> MemoryBackend:
    return MemoryBackend()


def _run(
    backend: MemoryBackend,
    run_id: str,
    config: str,
    user: str,
    minutes: int,
    stats: dict[str, Any] | None = None,
    finish: bool = True,
    complete: bool = True,
) -> None:
    at = T + timedelta(minutes=minutes)
    record = RunRecord(run_id, run_job_name(config, user), DAY, at)
    if finish:
        record = record.finish(at, complete=complete, stats=stats or {})
    ResultWriter(backend).save_run(record)


def test_every_run_of_any_status_newest_first_and_cut_to_the_limit(
    backend: MemoryBackend,
) -> None:
    _run(backend, "a", "momo", "site", 0, GOOD)
    _run(backend, "b", "mine", "local", 10, {**GOOD, "config_id": "mine", "user": "local"})
    _run(backend, "c", "momo", "local", 20, finish=False)
    _run(backend, "other", "nope", "site", 30)  # a config nobody declares: not listed
    ResultWriter(backend).save_run(RunRecord("edge", "edge-eval:drift:site", DAY, T))
    ctx = stores(backend, docs=DOCS_WITH_MINE)
    runs = load_screener_runs(ctx)
    assert [(r.run_id, r.owner, r.config_id) for r in runs] == [
        ("c", "local", "momo"), ("b", "local", "mine"), ("a", "site", "momo"),
    ]  # fmt: skip
    assert [r.run_id for r in load_screener_runs(ctx, 1)] == ["c"]


def test_filters_by_owner_screener_and_status(backend: MemoryBackend) -> None:
    _run(backend, "a", "momo", "site", 0, GOOD)
    _run(backend, "b", "mine", "local", 10, GOOD)
    _run(backend, "c", "momo", "local", 20, finish=False)
    _run(backend, "d", "momo", "local", 30, GOOD, complete=False)
    ctx = stores(backend, docs=DOCS_WITH_MINE)
    ids = lambda **kw: [r.run_id for r in load_screener_runs(ctx, **kw)]  # noqa: E731
    assert ids(user="local") == ["d", "c", "b"]
    assert ids(user="site") == ["a"]
    assert ids(screener="mine") == ["b"]
    assert ids(status="running") == ["c"]
    assert ids(user="local", screener="momo", status="partial") == ["d"]


def test_what_the_record_says_and_a_run_that_never_finished_has_no_decisions(
    backend: MemoryBackend,
) -> None:
    _run(backend, "a", "momo", "site", 0, GOOD)
    _run(backend, "live", "momo", "local", 5, finish=False)
    _run(backend, "bare", "momo", "local", 10, {})
    ctx = stores(backend, docs=DOCS_WITH_MINE)
    done = load_screener_run(ctx, "a")
    assert done is not None
    assert (done.status, done.session, done.config_version, done.config_hash) == (
        "complete", DAY, 3, "h1",
    )  # fmt: skip
    assert done.decisions is not None
    assert [(d.decision, d.count) for d in done.decisions] == [
        ("REJECT", 9), ("QUALIFIED", 4), ("PAUSED", 2),
    ]  # fmt: skip
    assert (done.picked, done.paused, done.regime, done.coverage) == (4, 2, "CALM", "PARTIAL")
    assert (done.missing_tables, done.missing_optional_tables) == (
        ("rollups/ibkr_iv",), ("rollups/other",),
    )  # fmt: skip
    assert len(done.unavailable) == 2 and done.knowledge_ts == T
    live = load_screener_run(ctx, "live")
    assert (
        live is not None
        and live.status == "running"
        and live.knowledge_ts == T + timedelta(minutes=5)
    )
    assert (live.decisions, live.picked, live.paused, live.finished_at) == (None, None, None, None)
    assert (live.config_version, live.config_hash, live.regime, live.coverage) == (
        None, None, None, None,
    )  # fmt: skip
    assert (live.config_id, live.owner, live.unavailable) == ("momo", "local", ())
    bare = load_screener_run(ctx, "bare")
    assert bare is not None and bare.decisions is None  # finished, but no summary: not 0


def test_one_run_by_id_never_another_jobs(backend: MemoryBackend) -> None:
    _run(backend, "a", "momo", "site", 0, GOOD)
    ResultWriter(backend).save_run(RunRecord("edge", "edge-eval:drift:site", DAY, T))
    ctx = stores(backend)
    assert load_screener_run(ctx, "edge") is None
    assert load_screener_run(ctx, "missing") is None
    assert load_screener_run(ctx, "../bad") is None
    assert load_screener_run_changes(ctx, "edge") is None


def _freeze(backend: MemoryBackend, run_id: str, **changes: Any) -> None:
    row: dict[str, Any] = {
        "user_id": "site", "config_id": "momo", "config_hash": "h1", "config_version": 3,
        "rows": 15, "passed": 4, "picked": 4, "paused": 2, "decision_names": ["QUALIFIED"],
        "decision_counts": [4], "regime": "CALM", "size_multiplier": 1.0,
        "previous_run_id": "prev", "previous_session": date(2026, 9, 30),
        "previous_version": 2, "new_picks": 1, "dropped": 3,
        **changes,
    }  # fmt: skip
    frame = pd.DataFrame([row])
    for name in ("config_version", "previous_version", "new_picks", "dropped"):
        frame[name] = frame[name].astype("Int64")
    frame["session_date"] = DAY
    frame["knowledge_ts"] = pd.Timestamp(T)
    frame["source"] = "test"
    frame["run_id"] = run_id
    ResultWriter(backend).write_result("screen_runs", DAY, run_id, frame)


def test_the_changes_are_the_runs_own_frozen_row_and_none_without_one(
    backend: MemoryBackend,
) -> None:
    _run(backend, "a", "momo", "site", 0, GOOD)
    _run(backend, "b", "momo", "site", 10, GOOD)
    _freeze(backend, "a")
    ctx = stores(backend)
    found = load_screener_run_changes(ctx, "a")
    assert found is not None
    assert (found.picked, found.paused, found.previous_run_id, found.previous_session) == (
        4, 2, "prev", date(2026, 9, 30),
    )  # fmt: skip
    assert (found.previous_version, found.new_picks, found.dropped) == (2, 1, 3)
    assert load_screener_run_changes(ctx, "b") is None  # no row of its own: never 0, never a's


def test_a_frozen_run_with_no_previous_run_has_no_counts(backend: MemoryBackend) -> None:
    _run(backend, "a", "momo", "site", 0, GOOD)
    _freeze(
        backend, "a", previous_run_id=None, previous_session=None, previous_version=None,
        new_picks=None, dropped=None,
    )  # fmt: skip
    found = load_screener_run_changes(stores(backend), "a")
    assert found is not None
    assert (found.previous_run_id, found.new_picks, found.dropped) == (None, None, None)


def test_a_small_limit_does_not_read_the_older_windows(backend: MemoryBackend) -> None:
    today = datetime.now(UTC).date()
    for n, back in enumerate((1, 3, 200)):
        day = today - timedelta(days=back)
        at = datetime.combine(day, T.timetz())
        record = RunRecord(f"r{n}", run_job_name("momo", "site"), day, at)
        ResultWriter(backend).save_run(record.finish(at, stats=GOOD))
    ctx = stores(backend)
    asked: list[tuple[date, date]] = []
    real = ctx.reader.runs_of

    def spy(jobs: Any, first: date, last: date) -> Any:
        asked.append((first, last))
        return real(jobs, first, last)

    ctx.reader.runs_of = spy  # type: ignore[method-assign]
    assert [r.run_id for r in load_screener_runs(ctx, 2)] == ["r0", "r1"]
    assert len(asked) == 1 and asked[0][1] == today  # the newest week filled the limit
    asked.clear()
    assert [r.run_id for r in load_screener_runs(ctx, 3)] == ["r0", "r1", "r2"]
    assert len(asked) > 1  # a bigger limit walks back to the old run
