"""The status of an on-request job: its owner or an admin reads it, a site job is shared, anyone
else's job reads as unknown (ADR 0037, amended)."""

import time

import pytest

from algotrade.config.user import UserContext
from algotrade.services.ondemand.screens import OnDemandScreens
from algotrade.services.ondemand.status import JobView, read_job
from algotrade.services.read.session import NotFoundError
from tests.helpers.ondemand_store import DAY, SCREEN, seeded_backend, site_configs

ALICE, BOB = UserContext("alice"), UserContext("bob")


def finished(runner: OnDemandScreens, job_id: str) -> JobView:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        found = read_job(runner, job_id, ALICE, admin=True)
        if found.state not in ("queued", "running"):
            return found
        time.sleep(0.02)
    raise AssertionError("the run did not finish")


def test_a_job_is_read_by_its_owner_or_an_admin_and_a_site_job_by_everyone() -> None:
    mine = {**SCREEN, "id": "mine"}
    runner = OnDemandScreens(
        seeded_backend(), site_configs({("alice", "strategies", "mine"): mine})
    )
    try:
        own = runner.request("mine", ALICE, DAY).job_id or ""
        shared = runner.request("big_liquid", ALICE, DAY).job_id or ""
        done = finished(runner, own)
        finished(runner, shared)
        assert (done.state, done.kind, done.user, done.session) == (
            "complete",
            "screen",
            "alice",
            DAY,
        )
        assert done.run_id
        assert read_job(runner, own, ALICE, admin=False).job_id == own
        assert read_job(runner, own, BOB, admin=True).job_id == own
        assert read_job(runner, shared, BOB, admin=False).user == "site"
        with pytest.raises(NotFoundError):  # another user's job reads as unknown
            read_job(runner, own, BOB, admin=False)
        with pytest.raises(NotFoundError):
            read_job(runner, "job-screen-nope", ALICE, admin=True)
    finally:
        runner.close()
