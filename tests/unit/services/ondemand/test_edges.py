"""An edge evaluation on request: a job under the owner's user, one at a time per user, the site's
only for an admin, stored like the CLI's (ADR 0059)."""

import threading
import time
from collections.abc import Iterator, Mapping
from typing import Any

import pytest

from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError, PermissionDeniedError
from algotrade.services.authoring.scope import ConflictError
from algotrade.services.evaluation.cross_section.harness import stored_outcome_sessions
from algotrade.services.jobs import JobContext
from algotrade.services.ondemand import edges as ondemand_edges
from algotrade.services.ondemand.edges import EvaluationRequest, OnDemandEdges
from algotrade.services.ondemand.status import read_job
from algotrade.services.read.session import NotFoundError
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.services.evaluation.cross_section.conftest import (
    ACTIVE,
    World,
    build_world,
    edge_document,
    screen,
)

ALICE, BOB = UserContext("alice"), UserContext("bob")


def configs() -> MemoryConfigStore:
    return MemoryConfigStore(
        {
            ("site", "selections", "active"): ACTIVE,
            ("site", "strategies", "momo"): screen(),
            ("site", "edges", "drift"): edge_document(),
        }
    )


def wait(runner: OnDemandEdges, request: EvaluationRequest, timeout: float = 20.0) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = read_job(runner, request.job_id, ALICE, admin=True)
        if found.state not in ("queued", "running"):
            return found
        time.sleep(0.02)
    raise AssertionError("the evaluation did not finish")


@pytest.fixture
def world() -> World:
    return build_world()


@pytest.fixture
def runner(world: World) -> Iterator[OnDemandEdges]:
    ondemand = OnDemandEdges(world.backend, configs())
    yield ondemand
    ondemand.close()


def test_a_request_starts_the_job_and_its_rows_are_keyed_by_the_user(
    runner: OnDemandEdges, world: World
) -> None:
    started = runner.request("drift", ALICE)
    assert started.state in ("queued", "running") and started.job_id and started.user == "alice"
    done = wait(runner, started)
    assert done.state == "complete" and done.run_id and done.exploratory is not None
    frame = world.reader.table_range("results/edge_eval", *world_range(world))
    assert frame is not None and set(frame["user_id"]) == {"alice"}


def world_range(world: World) -> tuple[Any, Any]:
    dates = world.reader.dates("results/edge_eval")
    return dates[0], dates[-1]


def test_a_second_request_while_one_runs_is_refused_until_it_finishes(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    gate = threading.Event()

    def blocked(params: Mapping[str, Any], ctx: JobContext) -> Mapping[str, Any]:
        gate.wait(10)
        return {"run_id": "r1", "exploratory": False}

    monkeypatch.setitem(ondemand_edges.LIBRARY_HANDLERS, "edge-eval", blocked)
    runner = OnDemandEdges(world.backend, configs())
    try:
        first = runner.request("drift", ALICE)
        with pytest.raises(ConflictError, match="already running for alice"):
            runner.request("drift", ALICE)
        runner.request("drift", BOB)  # another user's evaluation is not blocked by alice's
        gate.set()
        assert wait(runner, first).state == "complete"
        assert runner.request("drift", ALICE).job_id == first.job_id  # free again: runs again
    finally:
        gate.set()
        runner.close()


def test_only_an_admin_runs_as_the_site(runner: OnDemandEdges) -> None:
    with pytest.raises(PermissionDeniedError, match="admin"):
        runner.request("drift", ALICE, as_site=True)
    site = runner.request("drift", ALICE, as_site=True, admin=True)
    assert site.user == SITE_USER
    wait(runner, site)


def test_an_unknown_edge_and_an_empty_store_are_refused(world: World) -> None:
    runner = OnDemandEdges(world.backend, configs())
    try:
        with pytest.raises(NotFoundError, match="unknown edge"):
            runner.request("nope", ALICE)
    finally:
        runner.close()
    empty = OnDemandEdges(build_world(closed=[]).backend, configs())
    try:
        with pytest.raises(ConfigurationError, match="no outcomes"):
            empty.request("drift", ALICE)
    finally:
        empty.close()


def test_a_job_a_stopped_process_left_running_does_not_block_a_new_request(
    world: World,
) -> None:
    from datetime import UTC, datetime, timedelta  # noqa: PLC0415

    from algotrade.services.jobs import JobRecord, JobStatus, job_id_for  # noqa: PLC0415

    runner = OnDemandEdges(world.backend, configs())
    try:
        stored = stored_outcome_sessions(world.reader)
        params = {"edge": "drift", "start": stored[0].isoformat(), "end": stored[-1].isoformat()}
        old = datetime.now(UTC) - ondemand_edges.STALE - timedelta(minutes=1)
        dead = JobRecord(job_id_for("edge-eval", params, ALICE), "edge-eval", params, "alice", old)
        dead.status = JobStatus.RUNNING
        runner._writer.runs_backend.save(dead.to_run())
        started = runner.request("drift", ALICE)
        assert started.job_id == dead.job_id  # the same work: failed as abandoned, run again
        assert wait(runner, started).state == "complete"
    finally:
        runner.close()
