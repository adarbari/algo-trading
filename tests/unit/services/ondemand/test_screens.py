"""A screener run on request: the latest session unless it has run, stored like the nightly's,
under the writer lock, for the right owner (ADR 0033)."""

import time

import pytest

from algotrade.config.user import SITE_USER, UserContext
from algotrade.services.explore.store import NotFoundError
from algotrade.services.ondemand.screens import READY, OnDemandScreens, RunRequest
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.locks import held
from tests.helpers.ondemand_store import DAY, SCREEN, SNAPSHOT, seeded_backend, site_configs


def wait(runner: OnDemandScreens, request: RunRequest, timeout: float = 10.0) -> RunRequest:
    """Poll the job until it is no longer queued or running."""
    deadline = time.monotonic() + timeout
    assert request.job_id is not None
    while time.monotonic() < deadline:
        found = runner.status(request.config_id, request.job_id)
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
    started = runner.request("big_liquid", SITE, DAY)
    with pytest.raises(NotFoundError):
        runner.status("sma_trend", started.job_id or "")
    with pytest.raises(NotFoundError):
        runner.status("big_liquid", "job-screen-unknown")
    wait(runner, started)


def test_a_run_waits_for_the_ingest_lock(runner: OnDemandScreens) -> None:
    store = seeded_backend()
    ondemand = OnDemandScreens(store, site_configs())
    try:
        with held(store.lock("ingest")):
            request = ondemand.request("big_liquid", SITE, DAY)
            time.sleep(0.2)
            assert ondemand.status("big_liquid", request.job_id or "").state in (
                "queued",
                "running",
            )
        assert wait(ondemand, request).state == "complete"
    finally:
        ondemand.close()


def test_nothing_can_be_screened_before_any_data_is_stored() -> None:
    ondemand = OnDemandScreens(MemoryBackend(), site_configs())
    try:
        with pytest.raises(NotFoundError, match="no data"):
            ondemand.request("big_liquid", SITE)
    finally:
        ondemand.close()
