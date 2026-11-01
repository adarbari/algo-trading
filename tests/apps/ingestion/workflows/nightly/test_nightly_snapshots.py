"""A failed older session still lets the latest session take its snapshot steps (ADR 0086)."""

from collections.abc import Callable
from datetime import date

from algotrade_ingestion.workflows.nightly.nightly import SCREENS, run_nightly
from algotrade_ingestion.workflows.nightly.notify import message
from algotrade_ingestion.workflows.nightly.sessions import Plan, last_done
from tests.apps.ingestion.workflows.nightly.test_nightly import (
    D1,
    Calls,
    D,
    fake,  # noqa: F401
    statuses,
    steps_of,
    store,
)
from tests.helpers.ingest_fakes import task_ctx


def test_a_failed_older_session_still_takes_the_latest_sessions_snapshots(
    fake: Callable[..., Calls],  # noqa: F811
) -> None:
    """2026-10-26..31: rollups failed for the oldest session and the chains snapshot of the
    next one (the vendor serves only its current snapshot) was never fetched (ADR 0086)."""
    calls = fake(fail=("rollups",), on=D1)
    writer = store()
    plan = Plan([D1, D], last_done=date(2026, 9, 30), until=D)
    summary = run_nightly(task_ctx(writer), plan)
    assert summary["status"] == "FAILED" and summary["catch_up"]["held"] == [D.isoformat()]
    [snap] = summary["snapshot_runs"]
    assert snap["session"] == D.isoformat() and snap["status"] == "WAITING"  # held, not failing
    got = {n: s["status"] for n, s in snap["steps"].items()}
    assert got["chains"] == "SUCCEEDED" and got["universe-build"] == "SUCCEEDED"
    for downstream in ("bars", "rollups", SCREENS, "edge-picks"):
        assert got[downstream] == "NOT_RUN"
    assert calls.sessions("chains") == [D] and calls.sessions("bars") == [D1]
    assert calls.sessions("rollups") == [D1] and last_done(writer) is None
    # The older session clears: the snapshot is reused, never fetched again.
    calls.fail = ()
    again = run_nightly(task_ctx(writer), Plan([D1, D], last_done=date(2026, 9, 30), until=D))
    assert again["snapshot_runs"] == [] and again["status"] == "SUCCEEDED"
    assert calls.sessions("chains") == [D] and calls.sessions("universe-build") == [D]
    assert statuses(again)["chains"] == "SUCCEEDED" and last_done(writer) == D
    assert steps_of(again)["chains"]["reason"].startswith("succeeded in an earlier attempt")


def test_the_latest_session_takes_its_snapshots_past_the_catch_up_cap(
    fake: Callable[..., Calls],  # noqa: F811
) -> None:
    """The incident had six pending sessions and a cap of five: the latest was never in the
    plan, so no snapshot pass ran for it (architect review)."""
    calls = fake(fail=("rollups",), on=D1)
    writer = store()
    older = date(2026, 9, 29)
    plan = Plan([older, D1], [D], last_done=date(2026, 9, 28), until=D)
    summary = run_nightly(task_ctx(writer), plan)
    [snap] = summary["snapshot_runs"]
    assert snap["session"] == D.isoformat() and snap["steps"]["chains"]["status"] == "SUCCEEDED"
    assert calls.sessions("chains") == [D]


def test_a_failing_snapshot_step_in_the_pass_is_in_the_notice(
    fake: Callable[..., Calls],  # noqa: F811
) -> None:
    fake(fail=("rollups", "chains"), on=None)
    summary = run_nightly(task_ctx(store()), Plan([D1, D], last_done=date(2026, 9, 30), until=D))
    text = message(summary)
    assert f"chains failed (snapshot pass {D.isoformat()})" in text
    assert "bars not_run" not in text.split("snapshot pass")[-1]


def test_a_session_only_held_back_is_never_a_failed_record(fake: Callable[..., Calls]) -> None:  # noqa: F811
    """A pass whose snapshot steps succeeded must not read as a failing session (the
    disclosure of ADR 0062 would show it as FAILED_RETRYING)."""
    fake()
    writer = store()
    plan = Plan([date(2026, 9, 29)], [D1, D], last_done=date(2026, 9, 28), until=D)
    summary = run_nightly(task_ctx(writer), plan)  # clean catch-up cut by the cap
    [snap] = summary["snapshot_runs"]
    assert snap["status"] == "WAITING"
    [record] = writer.runs_for("nightly", D)
    assert record.status.value != "FAILED"
    assert last_done(writer) == date(2026, 9, 29)
