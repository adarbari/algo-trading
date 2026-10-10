"""An edge evaluation on request: a job under the owner's user, only of an edge the caller owns
(a site edge only as the site, by an admin), one at a time per owner across processes, stored like
the CLI's with ``trigger = ui`` (ADR 0059, amended 2026-10-10)."""

import threading
import time
from collections.abc import Iterator, Mapping
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError, PermissionDeniedError
from algotrade.services.authoring.scope import ConflictError
from algotrade.services.evaluation.cross_section.harness import stored_outcome_sessions
from algotrade.services.jobs import JobContext
from algotrade.services.jobs import exclusive as jobs_exclusive
from algotrade.services.jobs.exclusive import EdgeEvalBusyError, run_edge_eval_claimed
from algotrade.services.ondemand import edges as ondemand_edges
from algotrade.services.ondemand.edges import EvaluationRequest, OnDemandEdges
from algotrade.services.ondemand.status import read_job
from algotrade.services.read.session import NotFoundError
from algotrade.storage.backends.local import LocalBackend
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
            ("alice", "edges", "mine"): {"extends": "drift"},  # alice's clone of the site edge
            ("bob", "edges", "mine"): {"extends": "drift"},
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
    started = runner.request("mine", ALICE)
    assert started.state in ("queued", "running") and started.job_id and started.user == "alice"
    done = wait(runner, started)
    assert done.state == "complete" and done.run_id and done.exploratory is not None
    frame = world.reader.table_range("results/edge_eval", *world_range(world))
    assert frame is not None and set(frame["user_id"]) == {"alice"}
    stats = world.results.load_run(done.run_id).stats  # type: ignore[union-attr]
    assert (stats["owner"], stats["trigger"], stats["job_id"]) == ("alice", "ui", started.job_id)


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
        first = runner.request("mine", ALICE)
        with pytest.raises(ConflictError, match="already running for alice"):
            runner.request("mine", ALICE)
        runner.request("mine", BOB)  # another user's evaluation is not blocked by alice's
        gate.set()
        assert wait(runner, first).state == "complete"
        assert runner.request("mine", ALICE).job_id == first.job_id  # free again: runs again
    finally:
        gate.set()
        runner.close()


def test_a_user_runs_only_an_edge_they_own(runner: OnDemandEdges) -> None:
    with pytest.raises(PermissionDeniedError, match="not yours"):
        runner.request("drift", ALICE)  # a site edge: a trader has no way to run it
    with pytest.raises(PermissionDeniedError, match="Run as site"):
        runner.request("drift", ALICE, admin=True)  # an admin runs it as the site, not as himself
    with pytest.raises(NotFoundError, match="unknown edge"):
        runner.request("mine", UserContext("carol"))  # alice's and bob's clones are not hers


def test_only_an_admin_runs_a_site_edge_and_as_the_site(
    runner: OnDemandEdges, world: World
) -> None:
    with pytest.raises(PermissionDeniedError, match="admin"):
        runner.request("drift", ALICE, as_site=True)
    site = runner.request("drift", ALICE, as_site=True, admin=True)
    assert site.user == SITE_USER
    done = wait(runner, site)
    stats = world.results.load_run(done.run_id).stats  # type: ignore[union-attr]
    assert (stats["owner"], stats["trigger"]) == ("site", "ui")
    with pytest.raises(NotFoundError):  # as the site, a user's own edge is not visible
        runner.request("mine", ALICE, as_site=True, admin=True)


def test_the_check_and_submit_hold_the_stores_lock_across_processes(
    runner: OnDemandEdges, world: World
) -> None:
    other_process = world.backend.lock("edge-eval:alice")
    assert other_process.acquire(wait=False)
    try:
        with pytest.raises(ConflictError, match="another process"):
            runner.request("mine", ALICE)
        runner.request("mine", BOB)  # the lock is per owner
    finally:
        other_process.release()
    wait(runner, runner.request("mine", ALICE))


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
            empty.request("mine", ALICE)
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
        params = {
            "edge": "mine", "start": stored[0].isoformat(), "end": stored[-1].isoformat(),
            "trigger": "ui",
        }  # fmt: skip
        old = datetime.now(UTC) - ondemand_edges.STALE - timedelta(minutes=1)
        dead = JobRecord(job_id_for("edge-eval", params, ALICE), "edge-eval", params, "alice", old)
        dead.status = JobStatus.RUNNING
        runner._writer.runs_backend.save(dead.to_run())
        started = runner.request("mine", ALICE)
        assert started.job_id == dead.job_id  # the same work: failed as abandoned, run again
        assert wait(runner, started).state == "complete"
    finally:
        runner.close()


def test_the_cli_and_the_api_exclude_each_other_for_one_owner(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    gate, inside = threading.Event(), threading.Event()

    def blocked(params: Mapping[str, Any], ctx: JobContext) -> Mapping[str, Any]:
        inside.set()
        gate.wait(10)
        return {"run_id": "r1", "exploratory": False}

    monkeypatch.setitem(ondemand_edges.LIBRARY_HANDLERS, "edge-eval", blocked)
    runner = OnDemandEdges(world.backend, configs())
    params = {"edge": "mine", "start": "2026-01-01", "end": "2026-01-02", "trigger": "cli"}
    resources = {"reader": world.reader, "writer": world.results, "configs": configs()}
    try:
        first = runner.request("mine", ALICE)  # the API's job in flight: the CLI is refused
        with pytest.raises(EdgeEvalBusyError, match="already running for alice"):
            run_edge_eval_claimed(world.backend, resources, params, ALICE)
        gate.set()
        wait(runner, first)
        gate.clear()
        inside.clear()
        monkeypatch.setitem(jobs_exclusive.LIBRARY_HANDLERS, "edge-eval", blocked)
        cli = threading.Thread(
            target=run_edge_eval_claimed, args=(world.backend, resources, params, ALICE)
        )
        cli.start()  # the CLI's run in flight: the API is refused, another owner is not
        assert inside.wait(10)
        with pytest.raises(ConflictError, match="alice"):
            runner.request("mine", ALICE)
        gate.set()
        cli.join(10)
        runner.request("mine", ALICE)
    finally:
        gate.set()
        runner.close()


def test_two_runners_on_one_local_root_exclude_each_other(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The file lock and the shared run records, as two API processes see them."""
    gate = threading.Event()

    def blocked(params: Mapping[str, Any], ctx: JobContext) -> Mapping[str, Any]:
        gate.wait(10)
        return {"run_id": "r1", "exploratory": False}

    monkeypatch.setitem(ondemand_edges.LIBRARY_HANDLERS, "edge-eval", blocked)
    root = tmp_path / "store"
    local = LocalBackend(root)
    first = OnDemandEdges(local, configs())
    second = OnDemandEdges(LocalBackend(root), configs())
    try:
        with patch.object(ondemand_edges, "stored_outcome_sessions", lambda _r: [date(2026, 1, 5)]):
            started = first.request("mine", ALICE)
            with pytest.raises(ConflictError, match="already running for alice"):
                second.request("mine", ALICE)  # its record, read from the shared root
            other = LocalBackend(root).lock("edge-eval:bob")
            assert other.acquire(wait=False)  # a third process mid-claim for bob
            try:
                with pytest.raises(ConflictError, match="another process"):
                    second.request("mine", BOB)
            finally:
                other.release()
            gate.set()
            wait(first, started)
    finally:
        gate.set()
        first.close()
        second.close()
