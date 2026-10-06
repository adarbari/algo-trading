"""WAITING on publication (ADR 0043): a step whose source has not published the latest session
yet WAITS (not FAILED) until its deadline; the session is not done, so the next run resumes it;
a WAITING run alerts nobody."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from algotrade.config.site.settings import ConfigurationError, NightlySettings, SourcesSettings
from algotrade.config.user import SITE_USER, UserContext
from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.maintenance.quality import Check, check_chains
from algotrade_ingestion.workflows.nightly import screens as screens_module
from algotrade_ingestion.workflows.nightly.nightly import run_nightly, run_session
from algotrade_ingestion.workflows.nightly.notify import message, report
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
from tests.helpers.stored_frames import stamped

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


def test_stale_chain_checks_of_both_tiers_wait_before_the_deadline_and_fail_after() -> None:

    backend = MemoryBackend()
    rows = [
        {"instrument_id": f"EQ:{s}", "symbol": s, "tier": t, "status": "STALE_DATA: x"}
        for s, t in (("AAPL", "core"), ("ZZZ", "rest"))
    ]
    StoreWriter(backend).write_table("chains/status", D, "c", stamped(rows, D, "c"))

    checks = check_chains(StoreReader(backend), D, SourcesSettings.from_document({"quality": {
        "max_chain_stale_share": 0.1, "max_chain_stale_share_core": 0.1}}))  # fmt: skip
    stale = [c for c in checks if c.name.startswith("chains_stale_")]
    assert [(c.name, c.status, c.pending) for c in stale] == [
        ("chains_stale_core", "FAIL", True),
        ("chains_stale_rest", "FAIL", True),
    ]
    assert judge(stale, wait=True).status is StepStatus.WAITING  # before the deadline
    assert judge(stale, wait=False).status is StepStatus.FAILED  # at the deadline


def test_overall_waiting_unless_something_failed() -> None:
    def result(name: str, status: StepStatus) -> StepResult:
        return StepResult(name, status)

    waiting, ok = result("bars", StepStatus.WAITING), result("rates", StepStatus.SUCCEEDED)
    held = StepResult("rollups", StepStatus.NOT_RUN, held_by_wait=True)  # transitively too
    precondition = result("chains", StepStatus.NOT_RUN)  # e.g. no universe snapshot
    assert overall([ok, waiting, held]) is Status.WAITING
    assert overall([ok, waiting, precondition]) is Status.FAILED  # never masked by waiting
    assert overall([ok, waiting, held, precondition]) is Status.FAILED
    assert overall([ok, waiting, result("earnings", StepStatus.FAILED)]) is Status.FAILED
    assert overall([ok, held]) is Status.FAILED  # nothing is actually waiting
    assert overall([ok, waiting, {"status": "NOT_RUN", "held_by_wait": True}]) is Status.WAITING
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
    assert steps["rollups"]["held_by_wait"] and steps["screens"]["held_by_wait"]  # transitively
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


def test_a_waiting_run_that_also_finished_sessions_is_still_reported(tmp_path: Path) -> None:
    steps = {"bars": {"status": "WAITING", "critical": True}}
    runs = [
        {"session": D1.isoformat(), "status": "SUCCEEDED", "steps": {}},
        {"session": D.isoformat(), "status": "WAITING", "steps": steps},
    ]
    base = {"status": "WAITING", "sessions": [D1.isoformat(), D.isoformat()], "runs": runs}
    settings = NightlySettings.from_document({"notify": {"summary_path": str(tmp_path / "s.json")}})
    notifier = FakeNotifier()
    report(base, settings, notifier)
    assert len(notifier.notices) == 1  # D1 SUCCEEDED in this run: say so
    report({**base, "runs": runs[1:]}, settings, notifier)
    assert len(notifier.notices) == 1  # only the waiting session: quiet


# ----------------------------------------------------------------------------- arrivals / settle


def test_an_attempt_records_when_the_source_data_arrived(fake: Callable[..., Calls]) -> None:  # noqa: F811
    fake(
        checks={
            "bars": [NOT_YET],
            "chains": [Check("chains_stale_core", "PASS", "", data={"share": 0.05})],
        }
    )
    writer = store()
    summary = run_nightly(_ctx(writer, AFTER_CLOSE), Plan([D]))  # type: ignore[arg-type]
    steps = steps_of(summary)
    # 19:00 New York: three hours after D's 16:00 close
    assert steps["bars"]["arrival"] == {"minutes_after_close": 180.0, "published": False}
    assert steps["chains"]["arrival"] == {
        "minutes_after_close": 180.0,
        "published": True,
        "stale_share": 0.05,
    }
    assert "arrival" not in steps["earnings"]
    (record,) = writer.runs_for("nightly", D)
    assert record.stats["steps"]["bars"]["arrival"]["published"] is False


def test_a_catch_up_session_records_no_arrival(fake: Callable[..., Calls]) -> None:  # noqa: F811
    fake(checks={"bars": [Check("bars_fresh", "PASS", "")]})
    older = run_session(_ctx(store()), D1, latest=False)  # type: ignore[arg-type]
    assert "arrival" not in older["steps"]["bars"]


def test_chains_wait_without_fetching_until_the_settle_time(fake: Callable[..., Calls]) -> None:  # noqa: F811
    calls = fake()
    settings = NightlySettings.from_document({"steps": {"chains": {"settle_minutes": 240}}})
    writer = store()
    # 180 minutes after the close: chains wait for 240
    summary = run_nightly(_ctx(writer, AFTER_CLOSE), Plan([D]), settings)  # type: ignore[arg-type]
    steps = steps_of(summary)
    assert steps["chains"]["status"] == "WAITING" and "settling" in steps["chains"]["reason"]
    assert "arrival" not in steps["chains"]  # nothing fetched, nothing observed
    assert calls.sessions("chains") == [] and calls.sessions("bars") == [D]
    assert steps["rollups"]["held_by_wait"] and summary["status"] == "WAITING"

    later = datetime(2026, 10, 3, 0, 1, tzinfo=UTC)  # 240+ minutes after the close
    done = run_nightly(_ctx(writer, later), Plan([D]), settings)  # type: ignore[arg-type]
    assert statuses(done)["chains"] == "SUCCEEDED" and calls.sessions("chains") == [D]


def test_no_settle_time_is_the_current_behaviour(fake: Callable[..., Calls]) -> None:  # noqa: F811
    calls = fake()
    run_nightly(_ctx(store(), AFTER_CLOSE), Plan([D]))  # type: ignore[arg-type]
    assert calls.sessions("chains") == [D]
    assert NightlySettings().settle_for("chains") == 0
    assert (
        NightlySettings.from_document({"steps": {"chains": {"settle_minutes": 45}}}).settle_for(
            "chains"
        )
        == 45
    )
    with pytest.raises(ConfigurationError, match="settle_minutes"):
        NightlySettings.from_document({"steps": {"chains": {"settle_minutes": -1}}})
