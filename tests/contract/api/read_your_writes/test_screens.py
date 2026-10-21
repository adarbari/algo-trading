"""Read-your-writes of ``POST /screens/{id}/run`` (ADR 0077 decision 16): once the on-request run
is stored, the next ``ScreenerResults`` read (a run operation, keyed on the runs generation) shows
it. Every test runs with and without the process-local write epoch."""

import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from algotrade.config.user import UserContext
from algotrade.services.ondemand.screens import OnDemandScreens
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app
from tests.contract.api.read_your_writes.conftest import Gate
from tests.helpers.api_store import as_user, store_over
from tests.helpers.ondemand_store import DAY, seeded_backend, site_configs

RESULTS = """query ScreenerResults($date: Date) {
  screener(id: "big_liquid", date: $date) { latestRun { runId } }
}"""


@pytest.fixture
def client() -> Iterator[TestClient]:
    backend, configs = seeded_backend(), site_configs()
    app = create_app(
        ApiSettings("memory://", "config"),
        store_over(backend, configs, UserContext("local")),
        ondemand=OnDemandScreens(backend, configs),
        authenticator=as_user(),
    )
    with TestClient(app) as test_client:
        yield test_client


def test_a_run_shows_in_the_next_results_read(gate: Gate, client: TestClient) -> None:
    day = DAY.isoformat()
    assert gate.warm(client, RESULTS, date=day)["latestRun"] is None
    started = client.post("/screens/big_liquid/run", params={"date": day})
    assert started.status_code == 202
    deadline = time.monotonic() + 10
    while client.get(f"/jobs/{started.json()['job_id']}").json()["state"] in ("queued", "running"):
        assert time.monotonic() < deadline, "the run did not finish"
        time.sleep(0.02)
    assert gate.fresh(client, RESULTS, date=day)["latestRun"]["runId"]
