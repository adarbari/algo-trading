"""A screener run on request: the latest session unless it has run, stored like the nightly's,
without waiting for ingestion, for the right owner (ADR 0033)."""

import time
from datetime import timedelta

import pytest

from algotrade.config.user import SITE_USER, UserContext
from algotrade.services.ondemand.screens import READY, OnDemandScreens, RunRequest
from algotrade.services.ondemand.status import JobView, read_job
from algotrade.services.read.context import NotFoundError
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.locks import held
from algotrade.storage.runs import RunStatus
from tests.helpers.ondemand_store import DAY, SCREEN, SNAPSHOT, seeded_backend, site_configs


def wait(runner: OnDemandScreens, request: RunRequest, timeout: float = 10.0) -> JobView:
    """Poll the job (as an admin: ownership has its own test) until it is no longer queued or
    running."""
    deadline = time.monotonic() + timeout
    assert request.job_id is not None
    while time.monotonic() < deadline:
        found = read_job(runner, request.job_id, SITE, admin=True)
        if found.state not in ("queued", "running"):
            return found
        time.sleep(0.02)
    raise AssertionError(f"still {found.state} after {timeout} s")


@pytest.fixture
def runner() -> OnDemandScreens:
    ondemand = OnDemandScreens(seeded_backend(), site_configs())
    yield ondemand  # type: ignore[misc]
    ondemand.close()


SITE = UserContext(SITE_USER)


def test_a_request_runs_the_screen_stores_it_and_a_second_one_is_ready(
    runner: OnDemandScreens,
) -> None:
    started = runner.request("big_liquid", UserContext("alice"), DAY)
    assert started.state in ("queued", "running") and started.job_id and started.run_id is None
    done = wait(runner, started)
    assert (done.state, done.session) == ("complete", DAY) and done.run_id
    again = runner.request("big_liquid", UserContext("alice"), DAY)
    assert (again.state, again.job_id, again.run_id) == (READY, None, done.run_id)


def test_the_latest_session_with_data_is_the_default(runner: OnDemandScreens) -> None:
    request = runner.request("big_liquid", SITE)
    assert request.session == SNAPSHOT  # the newest stored reference snapshot
    assert wait(runner, request).state in ("partial", "complete")  # no features that day


def test_a_site_preset_runs_as_the_site_and_an_own_screen_as_its_user() -> None:
    mine = {**SCREEN, "id": "mine"}
    ondemand = OnDemandScreens(
        seeded_backend(), site_configs({("alice", "strategies", "mine"): mine})
    )
    try:
        site = wait(ondemand, ondemand.request("big_liquid", UserContext("alice"), DAY))
        own = wait(ondemand, ondemand.request("mine", UserContext("alice"), DAY))
        assert site.run_id and own.run_id
        jobs = ondemand._runs.runs_for("job:screen")
        assert sorted(r.stats["user"] for r in jobs) == ["alice", SITE_USER]
        with pytest.raises(NotFoundError):  # alice's screen is not bob's
            ondemand.request("mine", UserContext("bob"), DAY)
    finally:
        ondemand.close()


def test_only_a_screener_can_be_run_and_a_job_belongs_to_its_screener(
    runner: OnDemandScreens,
) -> None:
    with pytest.raises(NotFoundError, match="not a screener"):
        runner.request("sma_trend", SITE, DAY)
    with pytest.raises(NotFoundError):
        runner.request("nope", SITE, DAY)
    wait(runner, runner.request("big_liquid", SITE, DAY))


def test_a_run_does_not_wait_for_an_ingestion_run() -> None:
    """A backfill can hold the ingest lock for hours: a request must still be answered."""
    store = seeded_backend()
    ondemand = OnDemandScreens(store, site_configs())
    try:
        with held(store.lock("ingest")):
            request = ondemand.request("big_liquid", SITE, DAY)
            assert wait(ondemand, request, timeout=5).state == "complete"
    finally:
        ondemand.close()


def test_a_job_left_running_by_a_stopped_process_is_run_again() -> None:
    store = seeded_backend()
    first = OnDemandScreens(store, site_configs())
    try:
        stuck = first.request("big_liquid", SITE, DAY)
        wait(first, stuck)
    finally:
        first.close()
    # Simulate the process dying mid-run: the job record says running, long ago.
    job = first._runs.load_run(stuck.job_id or "")
    assert job is not None
    job.status = RunStatus.RUNNING
    job.finished_at = None
    job.started_at = job.started_at - timedelta(hours=2)
    first._runs.save_run(job)
    second = OnDemandScreens(store, site_configs())
    try:
        assert read_job(second, stuck.job_id or "", SITE, admin=True).state == "failed"
    finally:
        second.close()


def test_nothing_can_be_screened_before_any_data_is_stored() -> None:
    ondemand = OnDemandScreens(MemoryBackend(), site_configs())
    try:
        with pytest.raises(NotFoundError, match="no data"):
            ondemand.request("big_liquid", SITE)
    finally:
        ondemand.close()


def test_a_partial_run_is_run_again_on_request(
    runner: OnDemandScreens,
) -> None:
    """A PARTIAL run read a table with no rows for the session; the data may land later (a
    rollup backfilled after the screen rejected every row as missing, 2026-10-07), so "Run now"
    runs it again instead of reporting the stale run as ready."""
    first = wait(runner, runner.request("big_liquid", SITE, SNAPSHOT))
    assert first.state == "partial" and first.run_id  # no features that day
    again = runner.request("big_liquid", SITE, SNAPSHOT)
    assert again.state != READY and again.job_id
    assert wait(runner, again).state == "partial"  # ran again: still no features that day
