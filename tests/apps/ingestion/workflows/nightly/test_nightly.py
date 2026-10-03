"""The nightly workflow: step isolation, catch-up, screens as jobs, notification."""

import json
from collections.abc import Callable, Iterator, Mapping
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from algotrade.config.site.settings import NightlySettings, load_nightly
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.time.calendar import last_closed_session
from algotrade.services.jobs import JobContext, LocalJobRunner
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework import registry
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.workflows.nightly import screens as screens_module
from algotrade_ingestion.workflows.nightly.nightly import (
    FINALLY,
    NIGHTLY,
    SCREENS,
    nightly_job,
    run_nightly,
    run_session,
)
from algotrade_ingestion.workflows.nightly.sessions import Plan, last_done, plan_sessions
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.stored_frames import stamped, universe_rows

D = date(2026, 10, 2)
TASK_STEPS = [s.name for s in (*NIGHTLY, *FINALLY) if s.name != SCREENS]


class Calls:
    """Fake registry tasks: record (task, session); raise for the names in ``fail``."""

    def __init__(self, fail: tuple[str, ...] = (), partial: tuple[str, ...] = ()) -> None:
        self.calls: list[tuple[str, date]] = []
        self.fail, self.partial = fail, partial

    def task(self, name: str) -> Callable[[TaskContext, Mapping[str, Any]], RunRecord]:
        def run(ctx: TaskContext, params: Mapping[str, Any]) -> RunRecord:
            self.calls.append((name, params["session"]))
            if name in self.fail:
                raise RuntimeError(f"{name} broke")
            with IngestRun(ctx, f"fake-{name}", params["session"]) as r:
                r.stats["ran"] = name
                if name in self.partial:
                    r.partial("some items failed")
            return r.record

        return run

    def sessions(self, name: str) -> list[date]:
        return [s for n, s in self.calls if n == name]


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Calls]]:
    def install(**kwargs: tuple[str, ...]) -> Calls:
        calls = Calls(**kwargs)
        for name in TASK_STEPS:
            spec = registry.TASKS[name]
            fake_spec = replace(spec, run=calls.task(name), sources=(), skip=None)
            monkeypatch.setitem(registry.TASKS, name, fake_spec)
        return calls

    yield install


def store(universe_on: date | None = D) -> StoreWriter:
    writer = StoreWriter(MemoryBackend())
    if universe_on is not None:
        rows = stamped(universe_rows(["AAPL"]), universe_on, "u")
        writer.write_table("universe", universe_on, "u", rows)
    return writer


def steps_of(summary: Mapping[str, Any], i: int = -1) -> dict[str, Any]:
    return dict(summary["runs"][i]["steps"])


# ----------------------------------------------------------------------------- isolation


def test_a_failing_step_does_not_stop_later_steps(fake: Callable[..., Calls]) -> None:
    calls = fake(fail=("earnings",))
    summary = run_nightly(task_ctx(store()), Plan([D]))
    steps = steps_of(summary)
    assert steps["earnings"]["status"] == "FAILED"
    assert steps["earnings"]["error"] == "RuntimeError: earnings broke"
    assert [s for s in ("bars", "corporate-actions", "chains", "rollups", "quality") if
            steps[s]["status"] != "COMPLETE"] == []  # fmt: skip
    assert summary["status"] == "PARTIAL" and summary["steps"]["purge-raw"]["status"] == "COMPLETE"
    assert [n for n, _ in calls.calls][-2:] == ["quality", "purge-raw"]


def test_hard_dependencies_block_and_quality_and_purge_always_run(
    fake: Callable[..., Calls],
) -> None:
    calls = fake(fail=("chains",))
    writer = store()
    summary = run_nightly(task_ctx(writer), Plan([D]))
    steps = steps_of(summary)
    # Rollups still run (price stats and earnings need no chains); screens need both.
    assert steps["rollups"]["status"] == "COMPLETE" and calls.sessions("rollups") == [D]
    assert steps["screens"] == {
        "status": "BLOCKED",
        "duration_s": 0.0,
        "reason": "chains failed",
    }
    assert calls.sessions("quality") == [D]
    assert calls.sessions("purge-raw") == [D]
    record = writer.runs_for("nightly", D)[-1]
    assert record.status is RunStatus.PARTIAL and record.items["chains"] == "FAILED"


def test_chains_need_a_universe_snapshot_not_a_successful_build(
    fake: Callable[..., Calls],
) -> None:
    fake(fail=("universe-build",))
    steps = steps_of(run_nightly(task_ctx(store()), Plan([D])))
    assert steps["universe-build"]["status"] == "FAILED"
    assert steps["chains"]["status"] == "COMPLETE"  # yesterday's snapshot is enough
    empty = steps_of(run_nightly(task_ctx(store(universe_on=None)), Plan([D])))
    assert empty["chains"] == {
        "status": "BLOCKED",
        "duration_s": 0.0,
        "reason": f"no universe snapshot for {D}",
    }


def test_all_steps_failing_is_failed(fake: Callable[..., Calls]) -> None:
    fake(fail=tuple(TASK_STEPS))
    writer = store()
    summary = run_nightly(task_ctx(writer), Plan([D]))
    assert summary["status"] == "FAILED"
    assert writer.runs_for("nightly", D)[-1].status is RunStatus.FAILED


def test_partial_task_and_duration_warning(fake: Callable[..., Calls]) -> None:
    fake(partial=("bars",))
    ticks = iter(datetime(2026, 10, 3, 1, tzinfo=UTC) + timedelta(minutes=i) for i in range(999))
    ctx = task_ctx(store(), clock=lambda: next(ticks))
    summary = run_nightly(ctx, Plan([D]), NightlySettings(max_duration_minutes=5))
    assert steps_of(summary)["bars"]["status"] == "PARTIAL"
    assert steps_of(summary)["bars"]["duration_s"] > 0
    assert summary["status"] == "PARTIAL"
    assert summary["warnings"][0]["check"] == "nightly_duration"
    assert "alert above 5 min" in summary["warnings"][0]["detail"]


# ----------------------------------------------------------------------------- catch-up


def test_plan_sessions() -> None:
    assert plan_sessions(None, D, 5) == Plan([D])
    assert plan_sessions(D, D, 5) == Plan([], last_done=D)
    plan = plan_sessions(date(2026, 9, 25), D, 3)
    assert plan.sessions == [date(2026, 9, 30), date(2026, 10, 1), D]
    assert plan.dropped == [date(2026, 9, 28), date(2026, 9, 29)]
    holiday = plan_sessions(date(2026, 11, 25), date(2026, 11, 27), 5)  # over Thanksgiving
    assert holiday.sessions == [date(2026, 11, 27)]


def test_catch_up_runs_missed_sessions_and_chains_only_for_the_latest(
    fake: Callable[..., Calls],
) -> None:
    calls = fake()
    writer = store(date(2026, 9, 25))
    run_session(task_ctx(writer), date(2026, 9, 28), latest=True)
    assert last_done(writer) == date(2026, 9, 28)
    plan = plan_sessions(last_done(writer), D, 5)
    summary = run_nightly(task_ctx(writer), plan)
    missed = [date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1), D]
    assert summary["sessions"] == [d.isoformat() for d in missed]
    assert calls.sessions("bars")[1:] == missed
    assert calls.sessions("earnings")[1:] == missed
    assert calls.sessions("chains") == [date(2026, 9, 28), D]
    assert steps_of(summary, 0)["chains"]["status"] == "SKIPPED"
    assert steps_of(summary, 0)["universe-build"]["reason"].startswith("latest closed session")
    assert calls.sessions("purge-raw") == [D]
    assert last_done(writer) == D


def test_a_failed_nightly_is_retried(fake: Callable[..., Calls]) -> None:
    fake(fail=tuple(TASK_STEPS))
    writer = store()
    run_nightly(task_ctx(writer), Plan([D]))
    assert last_done(writer) is None


def test_woke_during_market_hours_ingests_nothing_new(fake: Callable[..., Calls]) -> None:
    calls = fake()
    writer = store()
    run_session(task_ctx(writer), date(2026, 10, 1), latest=True)
    until = last_closed_session(datetime(2026, 10, 2, 15, tzinfo=UTC))  # 11:00 New York
    plan = plan_sessions(last_done(writer), until, 5)
    summary = run_nightly(task_ctx(writer), plan)
    assert until == date(2026, 10, 1) and summary["sessions"] == []
    assert summary["status"] == "COMPLETE" and calls.sessions("chains") == [date(2026, 10, 1)]
    assert list(summary["steps"]) == ["purge-raw"]


# ----------------------------------------------------------------------------- jobs


def _scheduled(*ids: str) -> Callable[..., list[SimpleNamespace]]:
    configs = [
        SimpleNamespace(config=SimpleNamespace(id=i, kind="screener"), user=UserContext(u))
        for i, u in ((i, "alice" if i.startswith("a") else SITE_USER) for i in ids)
    ]
    configs.append(SimpleNamespace(config=SimpleNamespace(id="bt", kind="backtest")))
    return lambda store, schedule: configs


def _runner(
    writer: StoreWriter, configs: MemoryConfigStore, notifier: object = None
) -> tuple[LocalJobRunner, list[tuple[str, str, Mapping[str, Any]]]]:
    seen: list[tuple[str, str, Mapping[str, Any]]] = []

    def screen(params: Mapping[str, Any], ctx: JobContext) -> Mapping[str, Any]:
        seen.append((params["config"], ctx.user.user_id, params))
        if params["config"] == "broken":
            raise ValueError("no features")
        return {"coverage": "COMPLETE", "_partial": params["config"] == "a_thin"}

    resources = {
        "reader": task_ctx(writer).reader,
        "writer": writer,
        "configs": configs,
        "notifier": notifier,
    }
    handlers = {"screen": screen, "nightly": nightly_job}
    return LocalJobRunner(writer.runs_backend, handlers, resources, workers=1), seen


def _configs(tmp_path: Path, **notify: object) -> MemoryConfigStore:
    doc = {"notify": {"summary_path": str(tmp_path / "logs" / "latest.json"), **notify}}
    return MemoryConfigStore({("site", "settings", "nightly"): doc})


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def notify(self, title: str, message: str) -> None:
        self.sent.append((title, message))


def test_screens_are_submitted_as_jobs(
    fake: Callable[..., Calls], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake()
    monkeypatch.setattr(screens_module, "scheduled", _scheduled("site_one", "a_thin"))
    writer = store()
    runner, seen = _runner(writer, _configs(tmp_path), FakeNotifier())
    params = {"session": D.isoformat(), "catch_up": False, "export_dir": "out"}
    try:
        job = runner.wait(runner.submit("nightly", params, UserContext(SITE_USER)), timeout=10)
    finally:
        runner.shutdown()
    assert [(c, u) for c, u, _ in seen] == [("site_one", SITE_USER), ("a_thin", "alice")]
    assert seen[0][2] == {"config": "site_one", "session": D.isoformat(), "export_dir": "out"}
    step = job.result["runs"][0]["steps"]["screens"]
    assert step["status"] == "PARTIAL"
    assert [s["status"] for s in step["result"]["screens"]] == ["complete", "partial"]
    assert len(writer.runs_for("job:screen")) == 2
    assert job.status is RunStatus.PARTIAL and job.result["status"] == "PARTIAL"


def test_failed_screen_jobs_fail_the_step(
    fake: Callable[..., Calls], monkeypatch: pytest.MonkeyPatch
) -> None:
    fake()
    monkeypatch.setattr(screens_module, "scheduled", _scheduled("broken"))
    writer = store()
    runner, _ = _runner(writer, MemoryConfigStore({}))
    step = screens_module.screen_jobs(runner, MemoryConfigStore({}), None)(D)
    runner.shutdown()
    assert step.status.value == "FAILED"
    assert step.result["screens"][0]["error"] == "ValueError: no features"


# ----------------------------------------------------------------------------- notification


def test_notifies_on_non_complete_and_always_writes_the_summary(
    fake: Callable[..., Calls], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake(fail=("bars",))
    monkeypatch.setattr(screens_module, "scheduled", _scheduled())
    notifier = FakeNotifier()
    runner, _ = _runner(store(), _configs(tmp_path), notifier)
    try:
        runner.run("nightly", {"session": D.isoformat()}, UserContext(SITE_USER))
    finally:
        runner.shutdown()
    assert notifier.sent == [("algotrade nightly", f"PARTIAL ({D}): bars failed")]
    summary = json.loads((tmp_path / "logs" / "latest.json").read_text())
    assert summary["status"] == "PARTIAL" and summary["sessions"] == [D.isoformat()]


def test_complete_runs_and_disabled_notification_stay_quiet(
    fake: Callable[..., Calls], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = fake()
    monkeypatch.setattr(screens_module, "scheduled", _scheduled())
    quiet = FakeNotifier()
    runner, _ = _runner(store(), _configs(tmp_path), quiet)
    runner.run("nightly", {"session": D.isoformat()}, UserContext(SITE_USER))
    calls.fail = ("bars",)
    disabled = FakeNotifier()
    runner2, _ = _runner(store(), _configs(tmp_path, enabled=False), disabled)
    runner2.run("nightly", {"session": D.isoformat()}, UserContext(SITE_USER))
    runner.shutdown()
    runner2.shutdown()
    assert quiet.sent == [] and disabled.sent == []
    assert json.loads((tmp_path / "logs" / "latest.json").read_text())["status"] == "PARTIAL"


def test_nightly_settings() -> None:
    assert load_nightly(MemoryConfigStore({})) == NightlySettings()
    doc = {
        "sessions": {"settle_minutes": 10, "max_catch_up": 2},
        "alerts": {"max_duration_minutes": 20},
        "notify": {"enabled": False, "desktop": False, "summary_path": "x.json"},
    }
    s = load_nightly(MemoryConfigStore({("site", "settings", "nightly"): doc}))
    assert (s.settle_minutes, s.max_catch_up, s.max_duration_minutes) == (10, 2, 20.0)
    assert (s.notify_enabled, s.notify_desktop, s.summary_path) == (False, False, "x.json")
