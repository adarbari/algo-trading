"""What a nightly attempt records of each step beyond its result: when it began and the edges
it was defined with, so a read can place it in time and show what it needs and holds back."""

from collections.abc import Callable
from datetime import timedelta

from algotrade_ingestion.workflows.nightly.nightly import NIGHTLY, run_nightly
from algotrade_ingestion.workflows.nightly.sessions import Plan
from tests.apps.ingestion.workflows.nightly.test_nightly import (
    AFTER_CLOSE,
    Calls,
    D,
    fake,  # noqa: F401 - the fixture
    steps_of,
    store,
)
from tests.helpers.ingest_fakes import task_ctx


def test_every_step_records_the_edges_it_was_defined_with(fake: Callable[..., Calls]) -> None:  # noqa: F811
    fake()
    steps = steps_of(run_nightly(task_ctx(store()), Plan([D])))
    for step in NIGHTLY:
        recorded = steps[step.name]
        assert recorded["needs"] == list(step.needs), step.name
        assert recorded["reruns_after"] == list(step.reruns_after), step.name
    assert steps["rollups"]["needs"] and "ibkr-iv" in steps["rollups"]["reruns_after"]


def test_a_step_that_ran_records_when_it_began_and_a_held_one_does_not(
    fake: Callable[..., Calls],  # noqa: F811
) -> None:
    fake(fail=("bars",))
    steps = steps_of(run_nightly(task_ctx(store(), clock=lambda: AFTER_CLOSE), Plan([D])))
    assert steps["chains"]["started_at"] == AFTER_CLOSE.isoformat(timespec="seconds")
    assert "started_at" not in steps["rollups"]  # held by bars: never started


def test_a_reused_step_keeps_the_start_of_the_attempt_that_did_it(
    fake: Callable[..., Calls],  # noqa: F811
) -> None:
    fake(fail=("bars",))
    writer = store()
    first_at, later = AFTER_CLOSE, AFTER_CLOSE + timedelta(hours=2)
    run_nightly(task_ctx(writer, clock=lambda: first_at), Plan([D]))
    second = steps_of(run_nightly(task_ctx(writer, clock=lambda: later), Plan([D])))
    assert second["chains"]["origin"]
    assert second["chains"]["started_at"] == first_at.isoformat(timespec="seconds")
