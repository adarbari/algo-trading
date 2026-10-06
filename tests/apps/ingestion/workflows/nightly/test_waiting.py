"""WAITING on publication (ADR 0043): a step whose source has not published the latest session
yet WAITS (not FAILED) until its deadline; the session is not done, so the next run resumes it;
a WAITING run alerts nobody."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from algotrade.config.site.settings import NightlySettings
from algotrade.config.user import SITE_USER, UserContext
from algotrade.storage.runs import RunStatus
from algotrade_ingestion.tasks.maintenance.quality import Check
from algotrade_ingestion.workflows.nightly import screens as screens_module
from algotrade_ingestion.workflows.nightly.nightly import run_nightly, run_session
from algotrade_ingestion.workflows.nightly.notify import message
from algotrade_ingestion.workflows.nightly.render import _status
from algotrade_ingestion.workflows.nightly.sessions import Plan, last_done
from algotrade_ingestion.workflows.nightly.steps import (
    Status,
    StepResult,
    StepStatus,
    judge,
    overall,
)
from tests.apps.ingestion.workflows.nightly.test_nightly import (
    AFTER_CLOSE,
    D1,
    Calls,
    D,
    FakeNotifier,
    _configs,
    _nightly,
    _runner,
    fake,  # noqa: F401 - the fixture
    statuses,
    steps_of,
    store,
)
from tests.helpers.ingest_fakes import task_ctx

# 23:00 in Los Angeles on D (PDT, UTC-7) is 06:00 UTC the next day.
BEFORE_DEADLINE = AFTER_CLOSE  # 16:00 PT on D
AFTER_DEADLINE = datetime(2026, 10, 3, 6, 1, tzinfo=UTC)
NOT_YET = Check("bars_fresh", "FAIL", f"latest bars session {D1}, expected {D}", pending=True)


def _ctx(writer: object, now: datetime = BEFORE_DEADLINE) -> object:
    return task_ctx(writer, clock=lambda: now)  # type: ignore[arg-type]


def test_judge_waits_only_for_pending_failures_before_the_deadline() -> None:
    hard = Check("bars_count", "FAIL", "dropped")
    assert judge([NOT_YET], wait=True).status is StepStatus.WAITING
    assert judge([NOT_YET], wait=False).status is StepStatus.FAILED
    assert judge([NOT_YET, hard], wait=True).status is StepStatus.FAILED  # one real failure
    assert judge([hard], wait=True).status is StepStatus.FAILED
    assert judge([Check("x", "PASS", "ok")], wait=True).status is StepStatus.SUCCEEDED


def test_overall_waiting_unless_something_failed() -> None:
    def result(name: str, status: StepStatus) -> StepResult:
        return StepResult(name, status)

    waiting, held = result("bars", StepStatus.WAITING), result("rollups", StepStatus.NOT_RUN)
    ok = result("rates", StepStatus.SUCCEEDED)
    assert overall([ok, waiting, held]) is Status.WAITING
    assert overall([ok, waiting, result("earnings", StepStatus.FAILED)]) is Status.FAILED
    assert overall([ok, held]) is Status.FAILED  # held back by something that is not waiting
    assert (
        overall([ok, StepResult("shares", StepStatus.WAITING, critical=False)]) is Status.SUCCEEDED
    )
    assert overall([{"status": "WAITING", "critical": True}, ok]) is Status.WAITING


def test_a_pending_failure_waits_before_the_deadline_and_holds_dependents(
    fake: Callable[..., Calls],  # noqa: F811
) -> None:
    fake(checks={"bars": [NOT_YET]})
    writer = store()
    summary = run_nightly(_ctx(writer), Plan([D]))  # type: ignore[arg-type]
    steps = steps_of(summary)
    assert steps["bars"]["status"] == "WAITING"
    assert steps["bars"]["reason"].startswith("not published yet: bars_fresh")
    assert steps["rollups"]["reason"] == "needs bars (WAITING)"
    assert summary["status"] == "WAITING"
    (record,) = writer.runs_for("nightly", D)
    assert record.status is RunStatus.WAITING and record.items["bars"] == "WAITING"
    assert last_done(writer) is None  # not done: the next run resumes the session


def test_the_same_failure_fails_after_the_deadline(fake: Callable[..., Calls]) -> None:  # noqa: F811
    fake(checks={"bars": [NOT_YET]})
    summary = run_nightly(_ctx(store(), AFTER_DEADLINE), Plan([D]))  # type: ignore[arg-type]
    assert statuses(summary)["bars"] == "FAILED" and summary["status"] == "FAILED"


def test_a_step_deadline_overrides_the_site_deadline(fake: Callable[..., Calls]) -> None:  # noqa: F811
    fake(checks={"bars": [NOT_YET]})
    early = NightlySettings.from_document(
        {"schedule": {"data_deadline": "23:00"}, "steps": {"bars": {"deadline": "15:00"}}}
    )
    summary = run_nightly(_ctx(store()), Plan([D]), early)  # type: ignore[arg-type]
    assert statuses(summary)["bars"] == "FAILED"  # 16:00 PT is past bars' 15:00


def test_a_catch_up_session_is_past_its_deadline(fake: Callable[..., Calls]) -> None:  # noqa: F811
    fake(checks={"bars": [NOT_YET]})
    ctx = _ctx(store())
    older = run_session(ctx, D1, latest=False)  # type: ignore[arg-type]
    assert older["steps"]["bars"]["status"] == "FAILED" and older["status"] == "FAILED"


def test_a_real_failure_never_waits(fake: Callable[..., Calls]) -> None:  # noqa: F811
    fake(checks={"bars": [Check("bars_count", "FAIL", "dropped 40%")]})
    summary = run_nightly(_ctx(store()), Plan([D]))  # type: ignore[arg-type]
    assert statuses(summary)["bars"] == "FAILED"


def test_a_waiting_session_is_resumed_by_the_next_run(fake: Callable[..., Calls]) -> None:  # noqa: F811
    given = {"bars": [NOT_YET]}
    calls = fake(checks=given)
    writer = store()
    first = run_nightly(_ctx(writer), Plan([D]))  # type: ignore[arg-type]
    assert first["status"] == "WAITING"
    given["bars"] = []  # the source published
    second = run_nightly(_ctx(writer), Plan([D]))  # type: ignore[arg-type]
    assert second["status"] == "SUCCEEDED" and last_done(writer) == D
    assert calls.sessions("chains") == [D]  # succeeded in the first attempt: not refetched
    assert calls.sessions("bars") == [D, D]  # the waiting step ran again


def test_a_waiting_session_holds_the_later_ones_back(fake: Callable[..., Calls]) -> None:  # noqa: F811
    fake(checks={"bars": [NOT_YET]})
    early = datetime(2026, 10, 2, 5, tzinfo=UTC)  # 22:00 PT on D1: before D1's deadline
    summary = run_nightly(_ctx(store(), early), Plan([D1, D], until=D1))  # type: ignore[arg-type]
    assert summary["status"] == "WAITING" and summary["sessions"] == [D1.isoformat()]
    assert summary["catch_up"]["held"] == [D.isoformat()]


def test_a_snapshot_step_that_waited_expires_when_its_session_passes(
    fake: Callable[..., Calls],  # noqa: F811
) -> None:
    stale = Check("chains_stale", "FAIL", "53.5% stale (max 20%)", pending=True)
    fake(checks={"chains": [stale]})
    writer = store()
    first = run_nightly(_ctx(writer), Plan([D]))  # type: ignore[arg-type]
    assert statuses(first)["chains"] == "WAITING" and first["status"] == "WAITING"
    later = run_session(_ctx(writer, AFTER_DEADLINE), D, latest=False)  # type: ignore[arg-type]
    assert later["steps"]["chains"]["status"] == "FAILED"  # not skipped: it never succeeded
    assert "expired" in later["steps"]["chains"]["reason"]


def test_a_waiting_run_sends_no_alert_and_no_email(
    fake: Callable[..., Calls],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake(checks={"bars": [NOT_YET]})
    monkeypatch.setattr(screens_module, "nightly_screeners", _nightly())
    notifier = FakeNotifier()
    runner, _ = _runner(store(), _configs(tmp_path), notifier)
    try:
        runner.run("nightly", {"session": D.isoformat()}, UserContext(SITE_USER))
    finally:
        runner.shutdown()
    assert notifier.notices == []  # neither the desktop alert nor the email
    summary = json.loads((tmp_path / "logs" / "latest.json").read_text())
    assert summary["status"] == "WAITING"  # the summary file is still written
    assert message(summary).startswith(f"WAITING ({D}): bars waiting")


def test_waiting_has_a_label_colour_in_the_email() -> None:
    assert "#9a6700" in _status("WAITING")


def test_the_deadline_settings_are_typed() -> None:
    from algotrade.config.site.settings import ConfigurationError  # noqa: PLC0415

    assert NightlySettings().deadline_for("bars").isoformat() == "23:00:00"
    custom = NightlySettings.from_document(
        {"schedule": {"data_deadline": "22:30"}, "steps": {"chains": {"deadline": "23:45"}}}
    )
    assert custom.deadline_for("bars").isoformat() == "22:30:00"
    assert custom.deadline_for("chains").isoformat() == "23:45:00"
    for bad in ({"schedule": {"data_deadline": "25:00"}}, {"schedule": {"data_deadline": 2300}}):
        with pytest.raises(ConfigurationError, match="data_deadline"):
            NightlySettings.from_document(bad)
    with pytest.raises(ConfigurationError, match="unknown keys"):
        NightlySettings.from_document({"steps": {"bars": {"deadlin": "23:00"}}})
