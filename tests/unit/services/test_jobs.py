import threading
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.core.errors import AlgoTradeError, ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.jobs import JobContext, JobRecord, JobStatus, LocalJobRunner, job_id_for
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.storage.backends.config_files import MemoryConfigStore
from algotrade.storage.backends.memory import MemoryRuns

T0 = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
USER = UserContext("alice")


def make_runner(handlers: Mapping[str, Any], runs: MemoryRuns | None = None) -> LocalJobRunner:
    return LocalJobRunner(runs or MemoryRuns(), handlers, {"greeting": "hi"}, clock=lambda: T0)


def test_submit_wait_and_persisted_record() -> None:
    calls: list[Mapping[str, Any]] = []

    def echo(params: Mapping[str, Any], ctx: JobContext) -> Mapping[str, Any]:
        calls.append(params)
        return {"echo": params["x"], "who": ctx.user.user_id, "res": ctx.resources["greeting"]}

    runs = MemoryRuns()
    runner = make_runner({"echo": echo}, runs)
    job_id = runner.submit("echo", {"x": 1}, USER)
    job = runner.wait(job_id, timeout=5)
    assert job.status is JobStatus.COMPLETE
    assert job.result == {"echo": 1, "who": "alice", "res": "hi"}
    assert job.done and job.finished_at == T0
    assert runs.load(job_id) is not None
    # identical work is the same job and does not run again ...
    assert runner.submit("echo", {"x": 1}, USER) == job_id
    assert len(calls) == 1
    # ... unless explicitly forced; other params or users are different jobs
    runner.wait(runner.submit("echo", {"x": 1}, USER, force=True))
    assert len(calls) == 2
    assert runner.submit("echo", {"x": 2}, USER) != job_id
    assert job_id_for("echo", {"x": 1}, UserContext("bob")) != job_id
    runner.shutdown()


def test_failures_partials_and_retry() -> None:
    attempts = {"n": 0}

    def flaky(params: Mapping[str, Any], ctx: JobContext) -> Mapping[str, Any]:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise ValueError("vendor down")
        return {"ok": True, "_partial": True}

    runner = make_runner({"flaky": flaky})
    job_id = runner.submit("flaky", {}, USER)
    failed = runner.wait(job_id)
    assert failed.status is JobStatus.FAILED
    assert failed.error == "ValueError: vendor down"
    retried = runner.wait(runner.submit("flaky", {}, USER))  # failed jobs re-run on resubmit
    assert retried.status is JobStatus.PARTIAL
    assert retried.result == {"ok": True}
    runner.shutdown()


def test_in_flight_jobs_are_not_duplicated() -> None:
    gate = threading.Event()

    def slow(params: Mapping[str, Any], ctx: JobContext) -> Mapping[str, Any]:
        gate.wait(5)
        return {}

    runner = make_runner({"slow": slow})
    job_id = runner.submit("slow", {}, USER)
    assert runner.submit("slow", {}, USER, force=True) == job_id  # still running: no second copy
    assert runner.status(job_id).status in (JobStatus.QUEUED, JobStatus.RUNNING)
    gate.set()
    assert runner.wait(job_id).status is JobStatus.COMPLETE
    runner.shutdown()


def test_errors_and_recovery() -> None:
    runs = MemoryRuns()
    runner = make_runner({"noop": lambda p, c: {}}, runs)
    with pytest.raises(ConfigurationError, match="unknown job kind"):
        runner.submit("nope", {}, USER)
    with pytest.raises(AlgoTradeError, match="unknown job"):
        runner.status("job-missing")
    abandoned = JobRecord(
        "job-noop-x", "noop", {}, "alice", T0 - timedelta(hours=3), JobStatus.RUNNING
    )
    runs.save(abandoned.to_run())
    assert runner.recover(stale_after=timedelta(0), kinds=["other", "unknown"]) == []
    assert runner.recover(stale_after=timedelta(hours=1)) == ["job-noop-x"]
    recovered = runner.status("job-noop-x")
    assert recovered.status is JobStatus.FAILED
    assert "abandoned" in (recovered.error or "")
    assert runner.recover(stale_after=timedelta(hours=1)) == []
    assert runner.kinds == ("noop",)
    runner.shutdown()


def test_backtest_handler_on_golden_store(golden_reader: StoreReader) -> None:
    config = {
        "id": "bull_bh",
        "kind": "strategy",
        "impl": "buy_and_hold",
        "selection": {
            "name": "bull",
            "where": {"all": [{"field": "instrument.symbol", "op": "eq", "value": "BULL"}]},
        },
    }
    configs = MemoryConfigStore({("alice", "strategies", "bull_bh"): config})
    runner = LocalJobRunner(
        MemoryRuns(), LIBRARY_HANDLERS, {"reader": golden_reader, "configs": configs}
    )
    params = {"config": "bull_bh", "start": "2020-01-01", "end": "2022-12-31"}
    job = runner.wait(runner.submit("backtest", params, USER))
    assert job.status is JobStatus.COMPLETE, job.error
    assert job.result["selection"]["selected"] == 1
    assert job.result["metrics"]["num_trades"] == 1
    runner.shutdown()


def test_job_identity_follows_the_resolved_config(golden_reader: StoreReader) -> None:
    from algotrade.storage.backends.config_files import MemoryConfigStore  # noqa: PLC0415

    def config(fast_slow: tuple[int, int]) -> MemoryConfigStore:
        doc = {
            "id": "trend",
            "kind": "strategy",
            "impl": "sma_crossover",
            "params": {"fast": fast_slow[0], "slow": fast_slow[1]},
            "selection": {
                "name": "bull",
                "where": {"all": [{"field": "instrument.symbol", "op": "eq", "value": "BULL"}]},
            },
        }
        return MemoryConfigStore({("alice", "strategies", "trend"): doc})

    params = {"config": "trend", "start": "2020-01-01", "end": "2022-12-31"}
    first = LocalJobRunner(
        MemoryRuns(), LIBRARY_HANDLERS, {"reader": golden_reader, "configs": config((20, 100))}
    )
    same = LocalJobRunner(
        MemoryRuns(), LIBRARY_HANDLERS, {"reader": golden_reader, "configs": config((20, 100))}
    )
    edited = LocalJobRunner(
        MemoryRuns(), LIBRARY_HANDLERS, {"reader": golden_reader, "configs": config((10, 50))}
    )
    ids = [r.submit("backtest", params, USER) for r in (first, same, edited)]
    assert ids[0] == ids[1]  # same resolved config, dates and user: same job
    assert ids[0] != ids[2]  # editing the config is new work
    for runner, job_id in zip((first, same, edited), ids, strict=True):
        assert runner.wait(job_id).status is JobStatus.COMPLETE
        runner.shutdown()


def test_run_executes_in_the_callers_thread_and_children_go_through_the_runner() -> None:
    threads: list[str] = []

    def child(params: Mapping[str, Any], ctx: JobContext) -> Mapping[str, Any]:
        threads.append(threading.current_thread().name)
        return {"n": params["n"], "_partial": params["n"] == 2}

    def parent(params: Mapping[str, Any], ctx: JobContext) -> Mapping[str, Any]:
        assert ctx.jobs is not None
        kids = [ctx.jobs.run("child", {"n": n}, ctx.user, force=True) for n in (1, 2)]
        return {"kids": [k.status.value for k in kids]}

    runs = MemoryRuns()
    runner = LocalJobRunner(runs, {"child": child, "parent": parent}, {}, workers=1)
    try:
        job = runner.wait(runner.submit("parent", {}, USER), timeout=5)  # one worker: no deadlock
        assert job.result == {"kids": ["complete", "partial"]}
        assert len(runs.find("job:child")) == 2
        again = runner.run("child", {"n": 1}, USER)  # done and not forced: the existing job
        assert again.status is JobStatus.COMPLETE and len(threads) == 2
    finally:
        runner.shutdown()


def test_run_job_service_api_recovers_and_runs() -> None:
    from algotrade.services.jobs import run_job  # noqa: PLC0415

    runs = MemoryRuns()
    stuck = JobRecord(
        job_id_for("echo", {"x": 1}, USER), "echo", {"x": 1}, "alice", T0 - timedelta(9)
    )
    stuck.status = JobStatus.RUNNING
    runs.save(stuck.to_run())
    echo = lambda params, ctx: {"x": params["x"]}  # noqa: E731
    job = run_job(runs, {"echo": echo}, {}, "echo", {"x": 1}, USER, recover=("echo",))
    assert job.status is JobStatus.COMPLETE and job.result == {"x": 1}


def test_as_completed_yields_every_item_and_its_outcome() -> None:
    from algotrade.services.jobs import as_completed  # noqa: PLC0415

    def work(n: int) -> int:
        if n == 3:
            raise ValueError("three")
        return n * 10

    results: dict[int, object] = {}
    for item, outcome in as_completed(work, [1, 2, 3], workers=2):
        try:
            results[item] = outcome()
        except ValueError as exc:
            results[item] = str(exc)
    assert results == {1: 10, 2: 20, 3: "three"}
