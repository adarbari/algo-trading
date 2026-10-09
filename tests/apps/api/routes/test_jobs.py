"""``GET /jobs/{job_id}``: one status read for every on-request job; the owner or an admin reads
it, a site job is shared, anyone else's job is 404 like an unknown id (ADR 0037, amended)."""

import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from algotrade.config.site.users import Role, UserRecord
from algotrade.config.user import UserContext
from algotrade.services.ondemand.screens import OnDemandScreens
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app
from tests.helpers.api_store import StubAuthenticator, as_user, store_over
from tests.helpers.ondemand_store import DAY, SCREEN, seeded_backend, site_configs

USERS = {
    "user": [
        {"id": u, "role": r} for u, r in (("alice", "trader"), ("bob", "trader"), ("ana", "admin"))
    ]
}


@pytest.fixture
def stub() -> StubAuthenticator:
    return as_user("alice", Role.TRADER)


@pytest.fixture
def client(stub: StubAuthenticator) -> Iterator[TestClient]:
    backend = seeded_backend()
    configs = site_configs(
        {
            ("alice", "strategies", "mine"): {**SCREEN, "id": "mine"},
            ("site", "settings", "users"): USERS,
        }
    )
    app = create_app(
        ApiSettings("memory://", "config"),
        store_over(backend, configs, UserContext("alice")),
        ondemand=OnDemandScreens(backend, configs),
        authenticator=stub,
    )
    with TestClient(app) as http:
        yield http


def finished(client: TestClient, job_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        body = client.get(f"/jobs/{job_id}").json()
        if body["state"] not in ("queued", "running"):
            return body  # type: ignore[no-any-return]
        time.sleep(0.02)
    raise AssertionError("the job did not finish")


def test_the_owner_reads_their_own_job(client: TestClient) -> None:
    job_id = client.post("/screens/mine/run", params={"date": DAY.isoformat()}).json()["job_id"]
    done = finished(client, job_id)
    assert (done["kind"], done["state"], done["user"]) == ("screen", "complete", "alice")
    assert done["session"] == DAY.isoformat() and done["run_id"]


def test_another_users_job_is_404_but_an_admin_reads_it(
    client: TestClient, stub: StubAuthenticator
) -> None:
    job_id = client.post("/screens/mine/run", params={"date": DAY.isoformat()}).json()["job_id"]
    finished(client, job_id)
    stub.user = UserRecord("bob", Role.TRADER)
    assert client.get(f"/jobs/{job_id}").status_code == 404
    stub.user = UserRecord("ana", Role.ADMIN)
    assert client.get(f"/jobs/{job_id}").status_code == 200


def test_a_site_job_is_shared_and_an_unknown_id_is_404(
    client: TestClient, stub: StubAuthenticator
) -> None:
    shared = client.post("/screens/big_liquid/run", params={"date": DAY.isoformat()}).json()
    finished(client, shared["job_id"])
    stub.user = UserRecord("bob", Role.TRADER)
    assert client.get(f"/jobs/{shared['job_id']}").status_code == 200
    assert client.get("/jobs/job-screen-nope").status_code == 404
    stub.user = UserRecord("ana", Role.ADMIN)
    assert client.get("/jobs/job-screen-nope").status_code == 404


def test_jobs_are_off_without_a_runner() -> None:
    backend, configs = seeded_backend(), site_configs()
    app = create_app(
        ApiSettings("memory://", "config"),
        store_over(backend, configs, UserContext("local")),
        authenticator=as_user(),
    )
    assert TestClient(app).get("/jobs/job-screen-x").status_code == 400
