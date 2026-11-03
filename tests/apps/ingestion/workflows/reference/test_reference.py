"""The reference workflow (ADR 0039, WF4): its steps, the per-step lock, yielding to a pending
nightly, the record it leaves, the due rule, the alert, and the launchd agent."""

import plistlib
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from algotrade.config.site.settings import NightlySettings
from algotrade.services.jobs.exclusive import RunLockedError
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.ops.schedule import REFERENCE_LABEL, reference_plist
from algotrade_ingestion.tasks.framework import registry
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.workflows.nightly.nightly import NIGHTLY
from algotrade_ingestion.workflows.reference import reference as ref
from algotrade_ingestion.workflows.reference.reference import (
    BUSY,
    MAX_ATTEMPTS,
    REFERENCE,
    REFERENCE_RUN,
    YIELDED,
    Week,
    due,
    nightly_pending,
    reference_notice,
    run_reference,
    week_state,
)
from tests.helpers.ingest_fakes import task_ctx

FRIDAY, NEXT_FRIDAY = date(2026, 10, 30), date(2026, 11, 6)
START = datetime(2026, 10, 30, 22, tzinfo=UTC)
SATURDAY = datetime(2026, 10, 31, 15, tzinfo=UTC)  # 11:00 New York
TUESDAY = datetime(2026, 11, 3, 15, tzinfo=UTC)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[str]]:
    """Fake reference tasks that complete (or raise, for ``fail``); -> the events, in order."""

    def install(fail: tuple[str, ...] = ()) -> list[str]:
        events: list[str] = []

        def task(name: str) -> Callable[[TaskContext, Mapping[str, Any]], RunRecord]:
            def run(ctx: TaskContext, params: Mapping[str, Any]) -> RunRecord:
                events.append(f"{name}:{params.get('weekly')}")
                if name in fail:
                    raise RuntimeError(f"{name} broke")
                with IngestRun(ctx, f"fake-{name}", params["session"]) as r:
                    r.stats["ran"] = name
                return r.record

            return run

        for step in REFERENCE:
            spec = replace(registry.TASKS[step.name], run=task(step.name), sources=(), skip=None)
            monkeypatch.setitem(registry.TASKS, step.name, spec)
        steps = tuple(replace(s, accept=(), accept_with=(), requires=None) for s in REFERENCE)
        monkeypatch.setattr(ref, "REFERENCE", steps)
        return events

    return install


def test_the_steps_are_the_reference_ones_all_optional_and_none_is_a_nightly_step() -> None:
    assert [s.name for s in REFERENCE] == [
        "company-details", "shares", "macro-calendar", "ibkr-contracts", "etf-holdings",
    ]  # fmt: skip
    assert not any(s.critical for s in REFERENCE)
    # the ETF daily files and the IBKR snapshot stay market-daily; the rest left it
    nightly = {s.name: s for s in NIGHTLY}
    assert nightly["etf-holdings"].params == {"daily_only": True}
    assert {"company-details", "shares", "macro-calendar", "ibkr-contracts"}.isdisjoint(nightly)
    assert "ibkr-contracts" not in nightly["ibkr-iv"].needs


def test_each_step_runs_in_its_own_lock_block_in_order_with_the_weekly_caps(
    fake: Callable[..., list[str]],
) -> None:
    events = fake()
    log: list[str] = []

    @contextmanager
    def hold() -> Iterator[None]:
        log.append("lock")
        yield
        log.append("unlock")

    writer = StoreWriter(MemoryBackend())
    summary = run_reference(task_ctx(writer), FRIDAY, NightlySettings(), hold=hold)
    assert [e.split(":")[0] for e in events] == [s.name for s in REFERENCE]
    assert log == ["lock", "unlock"] * len(REFERENCE)
    assert summary["status"] == "SUCCEEDED" and not summary["warnings"]
    assert [r.session_date for r in writer.runs_for(REFERENCE_RUN)] == [FRIDAY]
    weekly = {e for e in events if e.endswith(":True")}
    assert {"company-details:True", "shares:True", "etf-holdings:True"} <= weekly


def test_a_pending_nightly_stops_the_run_and_the_rest_is_not_run(
    fake: Callable[..., list[str]],
) -> None:
    events = fake()
    answers = iter([False, False, True, True, True])
    summary = run_reference(
        task_ctx(StoreWriter(MemoryBackend())), FRIDAY, pending=lambda: next(answers)
    )
    assert [e.split(":")[0] for e in events] == ["company-details", "shares"]
    steps = summary["steps"]
    assert {steps[n]["status"] for n in ("macro-calendar", "ibkr-contracts", "etf-holdings")} == {
        "NOT_RUN"
    }
    assert steps["etf-holdings"]["reason"] == YIELDED
    assert reference_notice(summary).status == "SUCCEEDED"  # yielding is no failure


def test_a_failed_step_is_a_warning_an_alert_and_the_run_goes_on(
    fake: Callable[..., list[str]],
) -> None:
    events = fake(fail=("shares",))
    summary = run_reference(task_ctx(StoreWriter(MemoryBackend())), FRIDAY)
    assert len(events) == len(REFERENCE)
    assert summary["steps"]["shares"]["status"] == "FAILED"
    assert [w["check"] for w in summary["warnings"]] == ["optional_step"]
    notice = reference_notice(summary)
    assert notice.status == "FAILED" and "shares" in notice.message


def test_a_taken_ingest_lock_is_busy_and_nothing_is_recorded(
    fake: Callable[..., list[str]],
) -> None:
    fake()

    @contextmanager
    def taken() -> Iterator[None]:
        raise RunLockedError("another ingest run is using this data store")
        yield  # pragma: no cover

    writer = StoreWriter(MemoryBackend())
    summary = run_reference(task_ctx(writer), FRIDAY, hold=taken)
    assert summary["status"] == BUSY and writer.runs_for(REFERENCE_RUN) == []


def record(session: date, statuses: Mapping[str, str], published: bool = True) -> RunRecord:
    steps = {n: {"status": s} for n, s in statuses.items()}
    rec = RunRecord(f"r-{session}-{len(statuses)}", REFERENCE_RUN, session, START)
    rec.finish(START + timedelta(minutes=5), stats={"steps": steps})
    if not published:
        rec.status = RunStatus.FAILED
    return rec


CLEAN = {"a": "SUCCEEDED", "b": "SKIPPED"}
FAILING = {"a": "SUCCEEDED", "b": "FAILED"}


def test_a_week_is_clean_after_a_run_with_no_failed_or_unrun_step() -> None:
    assert week_state([record(FRIDAY, CLEAN)], FRIDAY).clean
    assert not week_state([record(FRIDAY, FAILING)], FRIDAY).clean
    assert not week_state([record(FRIDAY, {"a": "NOT_RUN"})], FRIDAY).clean  # yielded
    assert not week_state([record(FRIDAY, CLEAN, published=False)], FRIDAY).clean
    assert not week_state([record(FRIDAY, CLEAN)], NEXT_FRIDAY).clean  # another ISO week


def test_the_overdue_clock_runs_from_the_last_clean_run_only() -> None:
    """A yielded or failed Sunday run must not hide an overdue week."""
    failed = record(FRIDAY, FAILING)
    assert week_state([failed], FRIDAY).newest is None
    clean = record(FRIDAY - timedelta(days=7), CLEAN)
    assert week_state([failed, clean], FRIDAY).newest == clean.started_at


def test_failed_runs_are_counted_per_week() -> None:
    week = week_state([record(FRIDAY, FAILING), record(FRIDAY, {"a": "NOT_RUN"})], FRIDAY)
    assert (week.clean, week.failed_attempts) == (False, 1)


@pytest.mark.parametrize(
    ("week", "now", "quiet", "expected"),
    [
        (Week(False, 0, None), SATURDAY, True, "weekend"),
        (Week(False, 0, START), SATURDAY, True, "weekend"),
        (Week(False, 0, START), TUESDAY, True, None),  # a weekday, not overdue: wait for Saturday
        (Week(False, 0, START - timedelta(days=9)), TUESDAY, True, "overdue"),
        (Week(False, 0, None), TUESDAY, True, "overdue"),  # a new store
        (Week(False, 0, None), SATURDAY, False, None),  # a nightly or post-session is pending
        (Week(True, 0, START), SATURDAY, True, None),  # this week's run was clean
        (Week(False, MAX_ATTEMPTS, START), SATURDAY, True, None),  # an outage waits a week
        (Week(False, MAX_ATTEMPTS - 1, START), SATURDAY, True, "weekend"),
    ],
)
def test_the_due_rule(week: Week, now: datetime, quiet: bool, expected: str | None) -> None:
    assert due(week, now, quiet) == expected


def test_the_weekend_is_new_york_time_not_utc() -> None:
    friday_evening_new_york = datetime(2026, 10, 31, 1, tzinfo=UTC)  # still Friday 21:00 in NY
    assert due(Week(False, 0, START), friday_evening_new_york, True) is None


def test_a_nightly_is_pending_until_the_last_closed_session_is_done() -> None:
    settings = NightlySettings()
    writer = StoreWriter(MemoryBackend())
    assert nightly_pending(writer, SATURDAY, settings)  # nothing done yet
    done = RunRecord("n", "nightly", FRIDAY, START)
    writer.save_run(done.finish(START + timedelta(hours=1)))
    assert not nightly_pending(writer, SATURDAY, settings)
    assert nightly_pending(writer, TUESDAY, settings)  # Monday closed since


def test_the_agent_runs_the_reference_command_on_saturday_at_load_and_on_a_watchdog(
    tmp_path: Path,
) -> None:
    agent = plistlib.loads(reference_plist(tmp_path, 3600))
    assert agent["Label"] == REFERENCE_LABEL
    assert agent["ProgramArguments"][-2:] == ["reference", "--wait"]
    assert agent["StartCalendarInterval"] == {"Weekday": 6, "Hour": 8, "Minute": 0}
    assert agent["RunAtLoad"] is True and agent["StartInterval"] == 3600
    assert agent["Nice"] == 10  # background priority like the other agents
    with pytest.raises(ValueError):
        reference_plist(tmp_path, 0)
