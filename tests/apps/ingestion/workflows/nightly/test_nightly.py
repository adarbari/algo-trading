"""The nightly workflow (ADR 0039): needs, acceptance, hold-back, resume, waivers, jobs."""

import json
from collections.abc import Callable, Iterator, Mapping, Sequence
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
from algotrade_ingestion.tasks.maintenance.quality import Check, check_macro
from algotrade_ingestion.workflows.nightly import nightly as nightly_module
from algotrade_ingestion.workflows.nightly import screens as screens_module
from algotrade_ingestion.workflows.nightly.nightly import (
    FINALLY,
    NIGHTLY,
    SCREENS,
    nightly_job,
    run_nightly,
    run_session,
)
from algotrade_ingestion.workflows.nightly.notify import Notice
from algotrade_ingestion.workflows.nightly.sessions import Plan, last_done, plan_sessions
from algotrade_ingestion.workflows.nightly.steps import StepStatus, from_record, judge
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.stored_frames import stamped, universe_rows

D = date(2026, 10, 2)
D1 = date(2026, 10, 1)
AFTER_CLOSE = datetime(2026, 10, 2, 23, tzinfo=UTC)  # 19:00 New York: D has closed
TASK_STEPS = [s.name for s in (*NIGHTLY, *FINALLY) if s.name != SCREENS]


class Calls:
    """Fake registry tasks: record (task, session); raise for the names in ``fail``, finish
    PARTIAL for those in ``partial``; ``on`` limits a failure to one session."""

    def __init__(
        self, fail: tuple[str, ...] = (), partial: tuple[str, ...] = (), on: date | None = None
    ) -> None:
        self.calls: list[tuple[str, date]] = []
        self.fail, self.partial, self.on = fail, partial, on

    def task(self, name: str) -> Callable[[TaskContext, Mapping[str, Any]], RunRecord]:
        def run(ctx: TaskContext, params: Mapping[str, Any]) -> RunRecord:
            session = params["session"]
            self.calls.append((name, session))
            if name in self.fail and self.on in (None, session):
                raise RuntimeError(f"{name} broke")
            with IngestRun(ctx, f"fake-{name}", session) as r:
                r.stats["ran"] = name
                if name in self.partial:
                    r.partial("some items failed")
            return r.record

        return run

    def sessions(self, name: str) -> list[date]:
        return [s for n, s in self.calls if n == name]


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Calls]]:
    """Fake tasks for every step; acceptance checks off unless ``checks`` gives a step's."""

    def install(checks: Mapping[str, Sequence[Check]] | None = None, **kwargs: Any) -> Calls:
        calls = Calls(**kwargs)
        for name in TASK_STEPS:
            spec = registry.TASKS[name]
            fake_spec = replace(spec, run=calls.task(name), sources=(), skip=None)
            monkeypatch.setitem(registry.TASKS, name, fake_spec)
        given = checks or {}

        def accept(name: str) -> tuple[Any, ...]:
            if name not in given:
                return ()
            return (lambda reader, session, settings: list(given[name]),)

        steps = tuple(replace(s, accept=accept(s.name)) for s in NIGHTLY)
        monkeypatch.setattr(nightly_module, "NIGHTLY", steps)
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


def statuses(summary: Mapping[str, Any], i: int = -1) -> dict[str, str]:
    return {n: s["status"] for n, s in steps_of(summary, i).items()}


# ----------------------------------------------------------------------------- the DAG


def test_steps_are_declared_after_what_they_need() -> None:
    seen: set[str] = set()
    for step in NIGHTLY:
        assert set(step.needs) <= seen, f"{step.name} runs before {set(step.needs) - seen}"
        seen.add(step.name)


def test_a_failed_critical_step_holds_back_its_dependents_only(
    fake: Callable[..., Calls],
) -> None:
    calls = fake(fail=("earnings",))
    writer = store()
    summary = run_nightly(task_ctx(writer), Plan([D]))
    steps = steps_of(summary)
    assert steps["earnings"]["status"] == "FAILED"
    assert steps["earnings"]["error"] == "RuntimeError: earnings broke"
    # Independent market data still runs (chains can be fetched only today) ...
    assert [statuses(summary)[s] for s in ("bars", "rates", "chains")] == ["SUCCEEDED"] * 3
    # ... but nothing that needs earnings runs on missing input.
    assert steps["rollups"] == {
        "status": "NOT_RUN",
        "critical": True,
        "duration_s": 0.0,
        "reason": "needs earnings (FAILED)",
    }
    assert steps["screens"]["status"] == "NOT_RUN"
    assert calls.sessions("rollups") == [] and calls.sessions("purge-raw") == [D]
    assert summary["status"] == "FAILED"
    record = writer.runs_for("nightly", D)[-1]
    assert record.status is RunStatus.FAILED and record.items["rollups"] == "NOT_RUN"
    assert "earnings: RuntimeError: earnings broke" in record.stats["failed_because"][0]
    assert last_done(writer) is None  # a FAILED session is retried


def test_an_optional_step_failing_is_a_warning(fake: Callable[..., Calls]) -> None:
    fake(fail=("shares", "descriptions"))
    writer = store()
    summary = run_nightly(task_ctx(writer), Plan([D]))
    assert statuses(summary)["shares"] == "FAILED"
    assert summary["status"] == "SUCCEEDED"
    record = writer.runs_for("nightly", D)[-1]
    assert record.status is RunStatus.COMPLETE and last_done(writer) == D
    assert record.items["shares"] == "WARN: FAILED (optional step)"
    details = [w["detail"] for w in summary["warnings"] if w["check"] == "optional_step"]
    assert details == [
        f"{D} shares: RuntimeError: shares broke",
        f"{D} descriptions: RuntimeError: descriptions broke",
    ]


def test_a_market_rollups_failure_never_holds_back_the_screens(
    fake: Callable[..., Calls],
) -> None:
    """ADR 0047: market-rollups needs rollups, is not critical, and the screens do not need it."""
    bad = Check("market_rollups", "FAIL", f"no MKT:US row for {D}: trend@v1")
    calls = fake(checks={"market-rollups": [bad]})
    summary = run_nightly(task_ctx(store()), Plan([D]))
    market = steps_of(summary)["market-rollups"]
    assert market["status"] == "FAILED" and market["critical"] is False
    assert market["reason"] == f"market_rollups: no MKT:US row for {D}: trend@v1"
    assert statuses(summary)["screens"] == "SKIPPED"  # reached (no screener in this store)
    assert summary["status"] == "SUCCEEDED" and calls.sessions("market-rollups") == [D]
    fake(fail=("market-rollups",))
    summary = run_nightly(task_ctx(store()), Plan([D]))
    assert statuses(summary)["market-rollups"] == "FAILED"
    assert statuses(summary)["screens"] == "SKIPPED" and summary["status"] == "SUCCEEDED"


def test_market_rollups_wait_for_the_rollups(fake: Callable[..., Calls]) -> None:
    calls = fake(fail=("rollups",))
    summary = run_nightly(task_ctx(store()), Plan([D]))
    market = steps_of(summary)["market-rollups"]
    assert (market["status"], market["reason"]) == ("NOT_RUN", "needs rollups (FAILED)")
    assert calls.sessions("market-rollups") == []


def test_chains_need_a_universe_snapshot_not_a_successful_build(
    fake: Callable[..., Calls],
) -> None:
    fake(fail=("universe-build",))
    summary = run_nightly(task_ctx(store()), Plan([D]))
    assert statuses(summary)["universe-build"] == "FAILED"
    assert statuses(summary)["chains"] == "SUCCEEDED"  # yesterday's snapshot is enough
    assert summary["status"] == "FAILED"  # the build is critical: screens wait for a retry
    empty = steps_of(run_nightly(task_ctx(store(universe_on=None)), Plan([D])))
    assert empty["chains"]["status"] == "NOT_RUN"
    assert empty["chains"]["reason"] == f"no universe snapshot for {D}"
    assert empty["screens"]["reason"] == "needs chains (NOT_RUN), rollups (NOT_RUN)"


# ----------------------------------------------------------------------------- acceptance


def test_a_failing_acceptance_check_fails_the_step(fake: Callable[..., Calls]) -> None:
    bad = Check("bars_fresh", "FAIL", f"latest bars session {D1}, expected {D}")
    warn = Check("bars_note", "WARN", "a warning")
    fake(checks={"bars": [bad, warn, Check("bars_count", "PASS", "ok")]})
    summary = run_nightly(task_ctx(store()), Plan([D]))
    bars = steps_of(summary)["bars"]
    assert bars["status"] == "FAILED"
    assert bars["reason"] == f"bars_fresh: latest bars session {D1}, expected {D}"
    assert [c["name"] for c in bars["checks"]] == ["bars_fresh", "bars_note"]  # not the PASS
    assert steps_of(summary)["rollups"]["reason"] == "needs bars (FAILED)"
    assert summary["status"] == "FAILED"


def test_warnings_alone_pass(fake: Callable[..., Calls]) -> None:
    fake(checks={"chains": [Check("chains_note", "WARN", "x")]})
    summary = run_nightly(task_ctx(store()), Plan([D]))
    assert statuses(summary)["chains"] == "SUCCEEDED" and summary["status"] == "SUCCEEDED"
    assert steps_of(summary)["chains"]["checks"][0]["status"] == "WARN"


def test_a_partial_task_names_its_failed_items() -> None:
    record = RunRecord("rollups-x", "rollups", D, AFTER_CLOSE, RunStatus.PARTIAL, AFTER_CLOSE)
    record.items = {
        "price_stats@v2": "FAILED: bars/1d: no bars for 2026-10-05 ... --date 2026-10-05",
        "earnings@v1": "OK: 1 sessions, 10 rows",
    }
    step = next(s for s in NIGHTLY if s.name == "rollups")
    outcome = from_record(record, step)
    assert outcome.status.value == "FAILED"
    assert outcome.reason == (
        "task finished partial: price_stats@v2: FAILED: bars/1d: no bars for 2026-10-05 ... "
        "--date 2026-10-05"
    )


def test_the_macro_step_is_optional_latest_only_and_before_the_market_rollups() -> None:
    names = [s.name for s in NIGHTLY]
    step = NIGHTLY[names.index("macro")]
    assert (step.critical, step.latest_only, step.needs) == (False, True, ())
    assert step.accept_with == (check_macro,) and step.accept == ()
    assert names.index("macro") < names.index("market-rollups")  # the regime reads it (RG3)
    # ... but never as a need: a failed macro step must not hold the regime back (ADR 0039)
    assert "macro" not in NIGHTLY[names.index("market-rollups")].needs


def test_a_failing_macro_step_still_runs_the_market_rollups(fake: Callable[..., Calls]) -> None:
    fake(fail=("macro",))
    summary = run_nightly(task_ctx(store()), Plan([D]))
    assert statuses(summary)["macro"] == "FAILED"
    assert statuses(summary)["market-rollups"] == "SUCCEEDED"


def test_a_failing_macro_step_only_warns(fake: Callable[..., Calls]) -> None:
    fake(fail=("macro",))
    summary = run_nightly(task_ctx(store()), Plan([D]))
    assert statuses(summary)["macro"] == "FAILED"
    assert summary["status"] == "SUCCEEDED"  # an optional step: screens and the rest still run
    assert statuses(summary)["rollups"] == "SUCCEEDED"
    assert [w["check"] for w in summary["warnings"]] == ["optional_step"]


def test_task_complete_steps_fail_on_a_partial_task(fake: Callable[..., Calls]) -> None:
    fake(partial=("rates", "bars"))
    summary = run_nightly(task_ctx(store()), Plan([D]))
    assert statuses(summary)["rates"] == "FAILED"
    assert steps_of(summary)["rates"]["reason"] == "task finished partial: some items failed"
    assert statuses(summary)["bars"] == "SUCCEEDED"  # bars: its checks decide


def test_a_critical_step_without_its_source_fails(
    fake: Callable[..., Calls], monkeypatch: pytest.MonkeyPatch
) -> None:
    fake()
    for name in ("bars", "shares"):
        spec = replace(registry.TASKS[name], sources=("massive_bars",))
        monkeypatch.setitem(registry.TASKS, name, spec)
    summary = run_nightly(task_ctx(store()), Plan([D]))
    assert steps_of(summary)["bars"]["status"] == "FAILED"
    assert steps_of(summary)["bars"]["reason"] == "massive_bars is not configured"
    assert steps_of(summary)["shares"]["status"] == "SKIPPED"  # optional: not applicable


def test_duration_warning(fake: Callable[..., Calls]) -> None:
    fake()
    ticks = iter(datetime(2026, 10, 3, 1, tzinfo=UTC) + timedelta(minutes=i) for i in range(999))
    ctx = task_ctx(store(), clock=lambda: next(ticks))
    summary = run_nightly(ctx, Plan([D]), NightlySettings(max_duration_minutes=5))
    assert steps_of(summary)["bars"]["duration_s"] > 0
    assert summary["warnings"][0]["check"] == "nightly_duration"
    assert "alert above 5 min" in summary["warnings"][0]["detail"]


# ----------------------------------------------------------------------------- sessions


def test_plan_sessions_takes_the_oldest_and_drops_none() -> None:
    assert plan_sessions(None, D, 5) == Plan([D], until=D)
    assert plan_sessions(D, D, 5) == Plan([], last_done=D, until=D)
    plan = plan_sessions(date(2026, 9, 25), D, 3)
    assert plan.sessions == [date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30)]
    assert plan.waiting == [D1, D] and plan.latest is None  # today's chains: a later run
    holiday = plan_sessions(date(2026, 11, 25), date(2026, 11, 27), 5)  # over Thanksgiving
    assert holiday.sessions == [date(2026, 11, 27)] and holiday.latest == date(2026, 11, 27)


def test_catch_up_runs_missed_sessions_and_chains_only_for_the_latest(
    fake: Callable[..., Calls],
) -> None:
    calls = fake()
    writer = store(date(2026, 9, 25))
    run_session(task_ctx(writer), date(2026, 9, 28), latest=True)
    assert last_done(writer) == date(2026, 9, 28)
    plan = plan_sessions(last_done(writer), D, 5)
    summary = run_nightly(task_ctx(writer), plan)
    missed = [date(2026, 9, 29), date(2026, 9, 30), D1, D]
    assert summary["sessions"] == [d.isoformat() for d in missed]
    assert calls.sessions("bars")[1:] == missed
    assert calls.sessions("rollups")[1:] == missed
    assert calls.sessions("chains") == [date(2026, 9, 28), D]
    assert statuses(summary, 0)["chains"] == "SKIPPED"
    assert steps_of(summary, 0)["universe-build"]["reason"].startswith("latest closed session")
    assert calls.sessions("purge-raw") == [D]
    assert last_done(writer) == D


def test_a_failed_session_holds_back_the_later_ones(fake: Callable[..., Calls]) -> None:
    calls = fake(fail=("bars",), on=D1)
    writer = store()
    run_session(task_ctx(writer), date(2026, 9, 30), latest=True)  # the last done session
    summary = run_nightly(task_ctx(writer), Plan([D1, D], last_done=date(2026, 9, 30), until=D))
    assert summary["status"] == "FAILED"
    assert summary["sessions"] == [D1.isoformat()]
    assert summary["catch_up"]["held"] == [D.isoformat()]
    assert calls.sessions("bars")[1:] == [D1] and writer.runs_for("nightly", D) == []
    assert calls.sessions("purge-raw") == [D1]
    assert last_done(writer) == date(2026, 9, 30)
    # Next run: the failed session comes first again.
    assert plan_sessions(last_done(writer), D, 5).sessions == [D1, D]


def test_a_retry_resumes_where_the_session_stopped(fake: Callable[..., Calls]) -> None:
    calls = fake(fail=("bars",))
    writer = store()
    run_nightly(task_ctx(writer), Plan([D]))
    calls.fail = ()
    summary = run_nightly(task_ctx(writer), Plan([D]))
    assert summary["status"] == "SUCCEEDED" and last_done(writer) == D
    assert calls.sessions("chains") == [D]  # done in the first attempt: not refetched
    assert calls.sessions("bars") == [D, D] and calls.sessions("rollups") == [D]
    first = writer.runs_for("nightly", D)[0].run_id
    assert steps_of(summary)["chains"]["reason"] == f"succeeded in an earlier attempt ({first})"
    rerun = run_nightly(task_ctx(writer), Plan([D]), resume=False)  # --force
    assert rerun["status"] == "SUCCEEDED" and calls.sessions("chains") == [D, D]


def test_a_snapshot_step_past_its_day_fails_until_waived(fake: Callable[..., Calls]) -> None:
    calls = fake(fail=("chains",))
    writer = store()
    run_nightly(task_ctx(writer), Plan([D]))  # D is the latest: chains tried, failed
    calls.fail = ()
    later = date(2026, 10, 5)
    summary = run_nightly(task_ctx(writer), Plan([D, later], last_done=D1, until=later))
    chains = steps_of(summary, 0)["chains"]
    assert chains["status"] == "FAILED" and chains["reason"].startswith("expired:")
    assert "--waive chains" in chains["reason"]
    assert summary["catch_up"]["held"] == [later.isoformat()]
    assert calls.sessions("chains") == [D]  # never refetched for an older session
    waived = run_nightly(task_ctx(writer), Plan([D]), waive={"chains": "Cboe outage"})
    assert waived["status"] == "SUCCEEDED"
    chains = steps_of(waived)["chains"]
    assert chains["status"] == "WAIVED" and chains["reason"].endswith(": Cboe outage")
    assert chains["reason"].startswith("waived by site at ")
    assert last_done(writer) == D
    again = run_nightly(task_ctx(writer), Plan([D]))  # the waiver is kept on a later attempt
    assert statuses(again)["chains"] == "WAIVED"


def test_records_from_before_adr_0039_are_not_resumed(fake: Callable[..., Calls]) -> None:
    calls = fake()
    writer = store()
    legacy = RunRecord("nightly-old", "nightly", D, AFTER_CLOSE, RunStatus.PARTIAL, AFTER_CLOSE)
    legacy.stats = {"steps": {"rollups": {"status": "COMPLETE", "duration_s": 1.0}}}
    writer.save_run(legacy)
    run_nightly(task_ctx(writer), Plan([D]))
    assert calls.sessions("rollups") == [D]  # recomputed, not taken from the old record


def test_a_step_only_held_back_is_not_expired_later(fake: Callable[..., Calls]) -> None:
    calls = fake(fail=("bars",))
    writer = store()
    first = run_nightly(task_ctx(writer), Plan([D]))  # screens held back behind bars
    assert statuses(first)["screens"] == "NOT_RUN"
    calls.fail = ()
    later = date(2026, 10, 5)
    summary = run_nightly(task_ctx(writer), Plan([D, later], last_done=D1, until=later))
    assert statuses(summary, 0)["screens"] == "SKIPPED"  # never tried: not "expired"
    assert summary["status"] == "SUCCEEDED" and last_done(writer) == later


def test_an_older_date_is_not_the_latest(fake: Callable[..., Calls], tmp_path: Path) -> None:
    calls = fake()
    writer = store(D1)
    runner, _ = _runner(writer, _configs(tmp_path), FakeNotifier())
    try:
        job = runner.run("nightly", {"session": D1.isoformat()}, UserContext(SITE_USER))
    finally:
        runner.shutdown()
    steps = job.result["runs"][0]["steps"]
    assert steps["chains"]["status"] == "SKIPPED" and calls.sessions("chains") == []
    assert calls.sessions("bars") == [D1]  # session data is still fetched for D1


def test_woke_during_market_hours_ingests_nothing_new(fake: Callable[..., Calls]) -> None:
    calls = fake()
    writer = store()
    run_session(task_ctx(writer), D1, latest=True)
    until = last_closed_session(datetime(2026, 10, 2, 15, tzinfo=UTC))  # 11:00 New York
    plan = plan_sessions(last_done(writer), until, 5)
    summary = run_nightly(task_ctx(writer), plan)
    assert until == D1 and summary["sessions"] == []
    assert summary["status"] == "SUCCEEDED" and calls.sessions("chains") == [D1]
    assert list(summary["steps"]) == ["purge-raw"]


# ----------------------------------------------------------------------------- jobs


def _nightly(*ids: str) -> Callable[..., list[SimpleNamespace]]:
    configs = [
        SimpleNamespace(config=SimpleNamespace(id=i, kind="screener"), user=UserContext(u))
        for i, u in ((i, "alice" if i.startswith("a") else SITE_USER) for i in ids)
    ]
    return lambda store: configs


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
        "clock": lambda: AFTER_CLOSE,  # D is the last closed session
    }
    handlers = {"screen": screen, "nightly": nightly_job}
    return LocalJobRunner(writer.runs_backend, handlers, resources, workers=1), seen


def _configs(tmp_path: Path, **notify: object) -> MemoryConfigStore:
    doc = {"notify": {"summary_path": str(tmp_path / "logs" / "latest.json"), **notify}}
    return MemoryConfigStore({("site", "settings", "nightly"): doc})


class FakeNotifier:
    def __init__(self, warning: str | None = None) -> None:
        self.notices: list[Notice] = []
        self.warning = warning

    @property
    def sent(self) -> list[tuple[str, str]]:
        """What a desktop notifier would show: alerts only (not SUCCEEDED runs)."""
        return [(n.title, n.message) for n in self.notices if n.alert]

    def notify(self, notice: Notice) -> str | None:
        self.notices.append(notice)
        return self.warning


def test_screens_are_submitted_as_jobs(
    fake: Callable[..., Calls], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake()
    monkeypatch.setattr(screens_module, "nightly_screeners", _nightly("site_one", "a_thin"))
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
    assert step["status"] == "FAILED"
    assert step["reason"] == "screeners not complete: a_thin partial"
    assert [s["status"] for s in step["result"]["screens"]] == ["complete", "partial"]
    assert len(writer.runs_for("job:screen")) == 2
    assert job.status is RunStatus.PARTIAL and job.result["status"] == "FAILED"


def test_failed_screen_jobs_fail_the_step(
    fake: Callable[..., Calls], monkeypatch: pytest.MonkeyPatch
) -> None:
    fake()
    monkeypatch.setattr(screens_module, "nightly_screeners", _nightly("broken"))
    writer = store()
    runner, _ = _runner(writer, MemoryConfigStore({}))
    step = screens_module.screen_jobs(runner, MemoryConfigStore({}), None)(D)
    runner.shutdown()
    assert step.status.value == "FAILED"
    assert step.result["screens"][0]["error"] == "ValueError: no features"


# ----------------------------------------------------------------------------- notification


def test_notifies_on_failure_and_always_writes_the_summary(
    fake: Callable[..., Calls], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake(fail=("bars",))
    monkeypatch.setattr(screens_module, "nightly_screeners", _nightly())
    notifier = FakeNotifier()
    runner, _ = _runner(store(), _configs(tmp_path), notifier)
    try:
        runner.run("nightly", {"session": D.isoformat()}, UserContext(SITE_USER))
    finally:
        runner.shutdown()
    expected = f"FAILED ({D}): bars failed; rollups not_run; screens not_run"
    assert notifier.sent == [("algotrade nightly", expected)]
    summary = json.loads((tmp_path / "logs" / "latest.json").read_text())
    assert summary["status"] == "FAILED" and summary["sessions"] == [D.isoformat()]
    # The notice carries the full report (the email body): subject, text and HTML.
    (note,) = notifier.notices
    assert note.subject == f"[algotrade] {D} nightly: FAILED · 4 steps with failures"
    assert "bars FAILED: RuntimeError: bars broke" in note.text
    assert note.html.startswith("<!doctype html>") and "bars broke" in note.html
    assert summary["started_at"] <= summary["finished_at"]


def test_delivery_problems_are_warnings_never_failures(
    fake: Callable[..., Calls], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake()
    monkeypatch.setattr(screens_module, "nightly_screeners", _nightly())
    notifier = FakeNotifier(warning="email not configured: set ALGOTRADE_NOTIFY_EMAIL_TO")
    runner, _ = _runner(store(), _configs(tmp_path), notifier)
    job = runner.run("nightly", {"session": D.isoformat()}, UserContext(SITE_USER))
    runner.shutdown()
    assert job.result["status"] == "SUCCEEDED" and job.status is RunStatus.COMPLETE
    warning = {"check": "notify", "status": "WARN", "detail": notifier.warning}
    assert job.result["warnings"] == [warning]
    written = json.loads((tmp_path / "logs" / "latest.json").read_text())
    assert written["warnings"] == [warning]
    assert [n.status for n in notifier.notices] == ["SUCCEEDED"]  # the email goes every night


class BrokenNotifier:
    def notify(self, notice: Notice) -> str | None:
        raise OSError("boom")


def test_a_raising_notifier_is_a_warning(
    fake: Callable[..., Calls], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake()
    monkeypatch.setattr(screens_module, "nightly_screeners", _nightly())
    runner, _ = _runner(store(), _configs(tmp_path), BrokenNotifier())
    job = runner.run("nightly", {"session": D.isoformat()}, UserContext(SITE_USER))
    runner.shutdown()
    assert job.result["warnings"][0]["detail"] == "notifier failed: OSError: boom"


def test_succeeded_runs_and_disabled_notification_stay_quiet(
    fake: Callable[..., Calls], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = fake()
    monkeypatch.setattr(screens_module, "nightly_screeners", _nightly())
    quiet = FakeNotifier()
    runner, _ = _runner(store(), _configs(tmp_path), quiet)
    runner.run("nightly", {"session": D.isoformat()}, UserContext(SITE_USER))
    calls.fail = ("bars",)
    disabled = FakeNotifier()
    runner2, _ = _runner(store(), _configs(tmp_path, enabled=False), disabled)
    runner2.run("nightly", {"session": D.isoformat()}, UserContext(SITE_USER))
    runner.shutdown()
    runner2.shutdown()
    assert quiet.sent == [] and disabled.notices == []
    assert [n.status for n in quiet.notices] == ["SUCCEEDED"]
    assert json.loads((tmp_path / "logs" / "latest.json").read_text())["status"] == "FAILED"


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
    assert (s.email_enabled, s.smtp_host, s.smtp_port, s.email_max_examples) == (
        False,
        "smtp.gmail.com",
        587,
        5,
    )
    email = {"enabled": True, "smtp_host": "mail.test", "smtp_port": 465, "max_examples": 2}
    s = load_nightly(
        MemoryConfigStore({("site", "settings", "nightly"): {"notify": {"email": email}}})
    )
    assert (s.email_enabled, s.smtp_host, s.smtp_port, s.email_max_examples) == (
        True,
        "mail.test",
        465,
        2,
    )


def test_acceptance_keeps_the_figures_of_a_check_even_when_it_passes() -> None:
    outcome = judge([Check("coverage_x", "PASS", "ok", data={"cells": []}), Check("b", "PASS", "")])
    assert outcome.status is StepStatus.SUCCEEDED
    assert outcome.checks == [
        {"name": "coverage_x", "status": "PASS", "detail": "ok", "data": {"cells": []}}
    ]
