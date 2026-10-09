"""``POST /edges/{id}/evaluate``: an evaluation on request, one at a time per user, the site's
for an admin only (ADR 0059); its job is read at ``GET /jobs/{id}`` (``test_jobs.py``)."""

import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from algotrade.config.site.users import Role, UserRecord
from algotrade.config.user import UserContext
from algotrade.services.ondemand.edges import OnDemandEdges
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app
from tests.helpers.api_store import StubAuthenticator, store_over
from tests.unit.services.evaluation.cross_section.conftest import (
    ACTIVE,
    build_world,
    edge_document,
    screen,
)

EVALUATE = "/edges/drift/evaluate"


@pytest.fixture
def stub() -> StubAuthenticator:
    return StubAuthenticator(UserRecord("alice", Role.TRADER))


@pytest.fixture
def client(stub: StubAuthenticator) -> Iterator[TestClient]:
    world = build_world()
    configs = MemoryConfigStore(
        {
            ("site", "selections", "active"): ACTIVE,
            ("site", "strategies", "momo"): screen(),
            ("site", "edges", "drift"): edge_document(),
            ("site", "settings", "users"): {
                "user": [{"id": "alice", "role": "trader"}, {"id": "ana", "role": "admin"}]
            },
        }
    )
    app = create_app(
        ApiSettings("memory://", "config"),
        store_over(world.backend, configs, UserContext("alice")),
        ondemand_edges=OnDemandEdges(world.backend, configs),
        authenticator=stub,
    )
    with TestClient(app) as test_client:
        yield test_client


def poll(client: TestClient, url: str) -> dict[str, object]:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        body = client.get(url).json()
        if body["state"] not in ("queued", "running"):
            return body  # type: ignore[no-any-return]
        time.sleep(0.02)
    raise AssertionError("the evaluation did not finish")


def test_an_evaluation_is_started_polled_and_stored_for_the_caller(client: TestClient) -> None:
    started = client.post(EVALUATE)
    assert started.status_code == 202, started.text
    body = started.json()
    assert body["user"] == "alice" and body["state"] in ("queued", "running")
    done = poll(client, f"/jobs/{body['job_id']}")
    assert done["state"] == "complete" and done["run_id"]


def test_a_trader_cannot_run_as_the_site_but_an_admin_can(
    client: TestClient, stub: StubAuthenticator
) -> None:
    assert client.post(EVALUATE, params={"as_site": "true"}).status_code == 403
    stub.user = UserRecord("ana", Role.ADMIN)
    site = client.post(EVALUATE, params={"as_site": "true"})
    assert site.status_code == 202 and site.json()["user"] == "site"
    poll(client, f"/jobs/{site.json()['job_id']}")


def test_what_cannot_be_run_is_refused(client: TestClient) -> None:
    assert client.post("/edges/nope/evaluate").status_code == 404


def test_evaluations_are_off_without_a_runner() -> None:
    world = build_world()
    configs = MemoryConfigStore({})
    app = create_app(
        ApiSettings("memory://", "config"),
        store_over(world.backend, configs, UserContext("alice")),
        authenticator=StubAuthenticator(UserRecord("alice", Role.TRADER)),
    )
    assert TestClient(app).post(EVALUATE).status_code == 400
