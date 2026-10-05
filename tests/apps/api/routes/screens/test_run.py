"""``POST /screens/{id}/run`` and its status: run on request, ready when stored (ADR 0033)."""

import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from algotrade.config.user import UserContext
from algotrade.services.explore.store import store_over
from algotrade.services.ondemand.screens import OnDemandScreens
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app
from tests.helpers.ondemand_store import DAY, seeded_backend, site_configs

RUN = "/screens/big_liquid/run"


@pytest.fixture
def client() -> Iterator[TestClient]:
    backend, configs = seeded_backend(), site_configs()
    store = store_over(backend, configs, UserContext("local"))
    app = create_app(
        ApiSettings("memory://", "config"), store, ondemand=OnDemandScreens(backend, configs)
    )
    with TestClient(app) as test_client:
        yield test_client


def poll(client: TestClient, url: str) -> dict[str, object]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        body = client.get(url).json()
        if body["state"] not in ("queued", "running"):
            return body  # type: ignore[no-any-return]
        time.sleep(0.02)
    raise AssertionError("the run did not finish")


def test_a_run_is_started_polled_and_then_ready_without_running_again(client: TestClient) -> None:
    started = client.post(RUN, params={"date": DAY.isoformat()})
    assert started.status_code == 202
    body = started.json()
    assert body["state"] in ("queued", "running") and body["session"] == DAY.isoformat()
    done = poll(client, f"{RUN}/{body['job_id']}")
    assert done["state"] == "complete" and done["run_id"]
    again = client.post(RUN, params={"date": DAY.isoformat()})
    assert again.status_code == 200
    assert (again.json()["state"], again.json()["job_id"]) == ("ready", None)
    # The run is in the store: the review table (GraphQL) reads it.
    query = 'query($d: Date) { screener(id: "big_liquid", date: $d) { latestRun { runId } } }'
    read = client.post("/graphql", json={"query": query, "variables": {"d": DAY.isoformat()}})
    assert read.json()["data"]["screener"]["latestRun"]["runId"] == done["run_id"]


def test_what_cannot_be_run_is_refused(client: TestClient) -> None:
    assert client.post("/screens/nope/run").status_code == 404
    assert client.post("/screens/sma_trend/run").status_code == 404  # a strategy
    assert client.get(f"{RUN}/job-screen-nope").status_code == 404


def test_runs_are_off_without_a_runner() -> None:
    backend, configs = seeded_backend(), site_configs()
    app = create_app(
        ApiSettings("memory://", "config"), store_over(backend, configs, UserContext("local"))
    )
    assert TestClient(app).post(RUN).status_code == 400
