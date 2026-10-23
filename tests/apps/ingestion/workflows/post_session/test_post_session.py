"""The post-session workflow (ADR 0070): its steps and locks, the one session it runs for, the
no-op, the skipped edge-eval, the record it leaves, and IBKR's verify skips."""

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.config.site.settings import NightlySettings
from algotrade.services.jobs.exclusive import RunLockedError
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord, RunStatus, start_run
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework import registry
from algotrade_ingestion.tasks.framework.run import (
    IngestRun,
    TaskContext,
    recover_unpublished,
    stamp,
)
from algotrade_ingestion.workflows.nightly.records import stored_post_session
from algotrade_ingestion.workflows.nightly.render import render_html, render_text
from algotrade_ingestion.workflows.nightly.report import build_report
from algotrade_ingestion.workflows.nightly.sessions import POST_STEPS
from algotrade_ingestion.workflows.nightly.steps import Outcome, StepStatus
from algotrade_ingestion.workflows.post_session import post_session as post_module
from algotrade_ingestion.workflows.post_session.post_session import (
    BUSY,
    EDGE_EVAL,
    EDGE_VERDICTS,
    LOCKED,
    POST_SESSION,
    pending_session,
    post_done,
    run_post_session,
    target_session,
)
from algotrade_sources.vendors.ibkr.gateway import GatewayConfig, IbkrMarketData
from algotrade_sources.vendors.ibkr.market_data import IbkrSource
from tests.helpers.ingest_fakes import task_ctx

D1, D = date(2026, 10, 1), date(2026, 10, 2)
START = datetime(2026, 10, 2, 22, tzinfo=UTC)


def test_the_steps_are_the_four_that_do_not_decide_the_session_all_optional() -> None:
    assert (
        [s.name for s in POST_SESSION]
        == list(POST_STEPS)
        == ["descriptions", "verify", EDGE_EVAL, EDGE_VERDICTS]
    )
    assert not any(s.critical for s in POST_SESSION)
    assert LOCKED == ("descriptions", "verify")  # the tasks that write tables
    assert EDGE_VERDICTS in registry.TASKS and EDGE_VERDICTS not in LOCKED  # after edge-eval
    assert EDGE_EVAL not in registry.TASKS  # a job step, claimed per owner, not the ingest lock


class Calls:
    """Fake registry tasks that complete (or raise, for ``fail``) and note the order they ran in."""

    def __init__(self, events: list[str], fail: tuple[str, ...] = ()) -> None:
        self.events, self.fail = events, fail

    def task(self, name: str) -> Callable[[TaskContext, Mapping[str, Any]], RunRecord]:
        def run(ctx: TaskContext, params: Mapping[str, Any]) -> RunRecord:
            self.events.append(name)
            if name in self.fail:
                raise RuntimeError(f"{name} broke")
            with IngestRun(ctx, f"fake-{name}", params["session"]) as r:
                r.stats["ran"] = name
            return r.record

        return run


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[str]]:
    """Fake descriptions and verify tasks (``only``: some), no acceptance checks; -> the events."""

    def install(fail: tuple[str, ...] = (), only: tuple[str, ...] = LOCKED) -> list[str]:
        events: list[str] = []
        calls = Calls(events, fail)
        for name in (*only, EDGE_VERDICTS):  # the last step always runs, as a fake
            fake_spec = replace(registry.TASKS[name], run=calls.task(name), sources=(), skip=None)
            monkeypatch.setitem(registry.TASKS, name, fake_spec)
        steps = tuple(replace(s, accept=()) for s in POST_SESSION)
        monkeypatch.setattr(post_module, "POST_SESSION", steps)
        return events

    return install


def writer_with_nightly(*days: date, outcomes: str = "SUCCEEDED") -> StoreWriter:
    """A store where the nightly of each of ``days`` finished COMPLETE."""
    writer = StoreWriter(MemoryBackend())
    for day in days:
        record = RunRecord(f"nightly-{day}", "nightly", day, START)
        steps = {"outcomes": {"status": outcomes, "critical": False}}
        writer.save_run(record.finish(START + timedelta(hours=1), stats={"steps": steps}))
    return writer


class FakeEvals:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def __call__(self, session: date) -> Outcome:
        self.events.append(EDGE_EVAL)
        return Outcome(StepStatus.SUCCEEDED, {"evaluations": [{"edge": "drift"}]})


def test_locked_steps_run_under_the_hold_and_edge_eval_after_it_is_released(
    fake: Callable[..., list[str]],
) -> None:
    events = fake()
    writer = writer_with_nightly(D)

    @contextmanager
    def hold() -> Iterator[None]:
        events.append("lock")
        yield
        events.append("unlock")

    summary = run_post_session(task_ctx(writer), D, NightlySettings(), FakeEvals(events), hold=hold)
    assert events == [
        "lock", "descriptions", "verify", "unlock", EDGE_EVAL, "lock", EDGE_VERDICTS, "unlock",
    ]  # fmt: skip
    assert summary["status"] == "SUCCEEDED" and list(summary["steps"]) == [
        s.name for s in POST_SESSION
    ]
    assert {s["status"] for s in summary["steps"].values()} == {"SUCCEEDED"}


def test_the_run_leaves_a_published_record_and_is_then_a_no_op(
    fake: Callable[..., list[str]],
) -> None:
    fake()
    writer = writer_with_nightly(D)
    assert pending_session(writer) == D and not post_done(writer, D)
    summary = run_post_session(task_ctx(writer), D, evals=FakeEvals([]))
    record = writer.load_run(summary["run_id"])
    assert record is not None and record.job == "post-session" and record.session_date == D
    assert record.status is RunStatus.COMPLETE and set(record.stats["steps"]) == {
        "descriptions", "verify", EDGE_EVAL, EDGE_VERDICTS
    }  # fmt: skip
    assert post_done(writer, D) and pending_session(writer) is None  # nothing left to do


def test_a_catch_up_runs_for_the_last_done_session_only() -> None:
    """Earlier sessions of a catch-up get no post-session run, as latest-only steps had none."""
    writer = writer_with_nightly(D1, D)
    assert target_session(writer) == D and pending_session(writer) == D
    writer.save_run(RunRecord("post-1", "post-session", D1, START).finish(START))
    assert pending_session(writer) == D  # a record of the earlier session does not count
    assert post_done(writer, D1) and not post_done(writer, D)
    assert pending_session(writer_with_nightly()) is None  # no nightly done yet: nothing to run for


def test_an_unpublished_post_session_record_is_run_again() -> None:
    writer = writer_with_nightly(D)
    writer.save_run(start_run("post-session", D, START))  # RUNNING: a crash left it
    failed = start_run("post-session", D, START + timedelta(minutes=5))
    failed.status = RunStatus.FAILED
    writer.save_run(failed)
    assert pending_session(writer) == D


def test_a_session_whose_outcomes_failed_reports_edge_eval_skipped_with_the_reason(
    fake: Callable[..., list[str]],
) -> None:
    events = fake()
    writer = writer_with_nightly(D, outcomes="FAILED")
    summary = run_post_session(task_ctx(writer), D, evals=FakeEvals(events))
    step = summary["steps"][EDGE_EVAL]
    assert step["status"] == "SKIPPED" and step["reason"] == f"outcomes FAILED for {D}"
    assert EDGE_EVAL not in events  # never submitted, never passed silently
    assert summary["status"] == "SUCCEEDED"


def test_edge_eval_without_a_job_runner_is_skipped_saying_so(
    fake: Callable[..., list[str]],
) -> None:
    fake()
    summary = run_post_session(task_ctx(writer_with_nightly(D)), D)
    assert summary["steps"][EDGE_EVAL]["reason"].startswith("no job runner")


def test_a_failed_step_is_a_warning_and_the_record_is_still_published(
    fake: Callable[..., list[str]],
) -> None:
    fake(fail=("verify",))
    writer = writer_with_nightly(D)
    summary = run_post_session(task_ctx(writer), D, evals=FakeEvals([]))
    assert summary["steps"]["verify"]["status"] == "FAILED"
    assert summary["steps"]["descriptions"]["status"] == "SUCCEEDED"  # the others still ran
    assert summary["steps"][EDGE_EVAL]["status"] == "SUCCEEDED"
    assert [w["check"] for w in summary["warnings"]] == ["optional_step"]
    assert "verify: RuntimeError: verify broke" in summary["warnings"][0]["detail"]
    assert post_done(writer, D)  # a failing optional step never makes the watchdog retry hourly
    record = writer.load_run(summary["run_id"])
    assert record is not None and record.items["verify"] == "WARN: FAILED (optional step)"


def test_edge_verdicts_runs_after_edge_eval_and_its_failure_is_only_a_warning(
    fake: Callable[..., list[str]],
) -> None:
    events = fake(fail=(EDGE_VERDICTS,))
    writer = writer_with_nightly(D)
    summary = run_post_session(task_ctx(writer), D, evals=FakeEvals(events))
    assert events.index(EDGE_EVAL) < events.index(EDGE_VERDICTS)
    assert summary["steps"][EDGE_VERDICTS]["status"] == "FAILED"
    assert summary["steps"][EDGE_EVAL]["status"] == "SUCCEEDED"
    assert [w["check"] for w in summary["warnings"]] == ["optional_step"]
    assert "edge-verdicts: RuntimeError" in summary["warnings"][0]["detail"]
    assert post_done(writer, D)  # an optional step never makes the watchdog retry


def test_edge_verdicts_runs_under_the_ingest_lock_and_is_skipped_when_it_is_taken(
    fake: Callable[..., list[str]],
) -> None:
    events = fake()
    writer = writer_with_nightly(D)
    entered = []

    @contextmanager
    def hold() -> Iterator[None]:
        entered.append(1)
        if len(entered) > 1:  # another ingest took the lock after the first block
            raise RunLockedError("another ingest run is using this data store")
        yield

    summary = run_post_session(task_ctx(writer), D, NightlySettings(), FakeEvals(events), hold=hold)
    step = summary["steps"][EDGE_VERDICTS]
    assert step["status"] == "SKIPPED" and "another ingest run" in step["reason"]
    assert EDGE_VERDICTS not in events  # nothing ran, so nothing was published unlocked
    assert summary["status"] == "SUCCEEDED" and not summary["warnings"]


def test_edge_verdicts_holds_the_lock_while_it_runs(fake: Callable[..., list[str]]) -> None:
    events = fake()

    @contextmanager
    def hold() -> Iterator[None]:
        events.append("lock")
        yield
        events.append("unlock")

    run_post_session(
        task_ctx(writer_with_nightly(D)), D, NightlySettings(), FakeEvals(events), hold=hold
    )
    assert events[-3:] == ["lock", EDGE_VERDICTS, "unlock"]


def test_a_taken_ingest_lock_is_busy_and_nothing_ran_nor_was_recorded(
    fake: Callable[..., list[str]],
) -> None:
    events = fake()
    writer = writer_with_nightly(D)

    @contextmanager
    def taken() -> Iterator[None]:
        raise RunLockedError("another ingest run is using this data store")
        yield  # pragma: no cover

    summary = run_post_session(task_ctx(writer), D, evals=FakeEvals(events), hold=taken)
    assert summary["status"] == BUSY and "ingest run" in summary["reason"]
    assert events == [] and not post_done(writer, D)
    assert writer.runs_for("post-session") == []  # a later start retries from scratch


def test_a_long_run_is_a_duration_warning() -> None:
    now = [START]

    def slow(session: date) -> Outcome:
        now[0] += timedelta(minutes=400)
        return Outcome(StepStatus.SUCCEEDED)

    ctx = task_ctx(writer_with_nightly(D), clock=lambda: now[0])
    summary = run_post_session(ctx, D, NightlySettings(post_max_duration_minutes=60), slow)
    assert [w["check"] for w in summary["warnings"]] == ["post_duration"]


def test_the_report_gets_a_post_session_section_from_the_stored_record(
    fake: Callable[..., list[str]],
) -> None:
    fake()
    writer = writer_with_nightly(D)
    nightly = {"status": "SUCCEEDED", "sessions": [D.isoformat()], "runs": [], "steps": {}}
    before = build_report(nightly, {})
    assert before.post_status == "" and before.post_steps == ()
    assert "POST-SESSION: not run yet" in render_text(before)
    run_post_session(task_ctx(writer), D, evals=FakeEvals([]))
    post = stored_post_session(task_ctx(writer).reader, D)
    assert post is not None and post["status"] == "SUCCEEDED"
    report = build_report(nightly, {}, post=post, max_post_duration_s=3600.0)
    assert report.post_status == "SUCCEEDED"
    assert [s.step for s in report.post_steps] == [
        "descriptions",
        "verify",
        EDGE_EVAL,
        EDGE_VERDICTS,
    ]
    text, html = render_text(report), render_html(report)
    assert "POST-SESSION: SUCCEEDED" in text and "edge-eval" in text
    assert "Post-session: SUCCEEDED" in html
    assert report.bad_steps == ()  # the nightly's own steps are not the post-session's


# ----------------------------------------------------------------------------- IBKR (ADR 0026)


def test_disabled_ibkr_skips_verify_and_descriptions_run_on(
    fake: Callable[..., list[str]],
) -> None:
    events = fake(only=("descriptions",))
    writer = writer_with_nightly(D)
    ctx = replace(task_ctx(writer), unavailable={"ibkr": "[ibkr] is disabled in sources.toml"})
    steps = run_post_session(ctx, D, evals=FakeEvals([]))["steps"]
    assert steps["verify"]["status"] == "SKIPPED"
    assert steps["verify"]["reason"] == "skipped: [ibkr] is disabled in sources.toml"
    assert events == ["descriptions", EDGE_VERDICTS]


@pytest.mark.allow_localhost
def test_an_unreachable_gateway_skips_verify_with_a_warn_and_a_hint(
    fake: Callable[..., list[str]],
) -> None:
    fake(only=("descriptions",))
    gateway = IbkrMarketData(GatewayConfig("127.0.0.1", 1, 1))  # nothing listens on port 1
    writer = writer_with_nightly(D)
    ctx = task_ctx(writer, sources={"ibkr": IbkrSource(gateway)})
    summary = run_post_session(ctx, D, evals=FakeEvals([]))
    verify = summary["steps"]["verify"]
    assert summary["status"] == "SUCCEEDED" and verify["status"] == "SKIPPED"
    assert verify["reason"].startswith("skipped: WARN: IB Gateway not reachable on 12")
    nightly = {"status": "SUCCEEDED", "sessions": [D.isoformat()], "runs": [], "steps": {}}
    report = build_report(nightly, {}, post=stored_post_session(ctx.reader, D))
    [line] = report.verification
    assert line.status == "SKIPPED" and "not reachable" in line.note
    assert any("IB Gateway (Read-Only API" in h for h in report.hints)
    assert "VERIFICATION VS IBKR" in render_text(report)
    assert "Verification vs IBKR" in render_html(report)


# ------------------------------------------------------ the risk: recovery and edge evaluations


def test_recovery_leaves_an_edge_evaluation_committing_outside_the_ingest_lock() -> None:
    """``recover_unpublished`` (a nightly's start) acts only on runs whose record is RUNNING /
    FAILED / WAITING, i.e. ingest runs: an edge evaluation writes its results pending with no
    run record (saved just before its commit), and its job record has another id, so a nightly
    starting while edge-eval runs outside the lock rolls nothing of it back."""
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    rows = stamp(pd.DataFrame({"instrument_id": ["EQ:A"], "value": [1.0]}), D, START, "t", "s")
    backend.tables.write("rollups/instrument/a@v1", D, "edge-eval-run", rows, pending=True)
    job = start_run("job:edge-eval", D, START)  # RUNNING: the job record, not the results run
    writer.save_run(job)
    assert recover_unpublished(writer, START) == {"completed": [], "dropped": []}
    assert backend.tables.pending_runs() == ["edge-eval-run"]


class Recorder:
    def __init__(self) -> None:
        self.notices: list[Any] = []

    def notify(self, notice: Any) -> None:
        self.notices.append(notice)


def test_a_failed_post_session_step_or_a_blown_budget_alerts_like_a_failed_nightly_step() -> None:
    steps = {"verify": {"status": "FAILED"}, "descriptions": {"status": "SUCCEEDED"}}
    failed = post_module.post_notice({"session": "2026-10-02", "steps": steps, "warnings": []})
    assert failed.alert and failed.message == "FAILED (2026-10-02): verify failed"
    slow = post_module.post_notice(
        {"session": "2026-10-02", "steps": {}, "warnings": [{"check": "post_duration"}]}
    )
    assert slow.alert and "duration budget" in slow.message
    ok = post_module.post_notice({"session": "2026-10-02", "steps": {}, "warnings": []})
    assert not ok.alert
    sent, summary = Recorder(), {"session": "2026-10-02", "status": "SUCCEEDED", **{"steps": steps}}
    summary["warnings"] = []
    post_module._notify(summary, sent, NightlySettings())
    assert [n.alert for n in sent.notices] == [True]
    quiet = Recorder()
    post_module._notify(summary, quiet, NightlySettings(notify_enabled=False))
    post_module._notify({**summary, "status": BUSY}, quiet, NightlySettings())
    assert quiet.notices == []
