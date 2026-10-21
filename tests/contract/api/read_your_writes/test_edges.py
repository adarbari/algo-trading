"""Read-your-writes of the edge write routes (ADR 0077 decision 16): copy, save, delete, state
and evaluate change what ``EdgesPage`` and ``PublishedEdge`` (cached per user) serve on the very
next read. Every test runs with and without the process-local write epoch (``conftest``)."""

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from algotrade.config.site.users import Role, UserRecord
from algotrade.config.user import UserContext
from algotrade.services.ondemand.edges import OnDemandEdges
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app
from tests.apps.api.routes.authoring.test_edges import SITE_EDGE
from tests.contract.api.read_your_writes.conftest import Gate
from tests.helpers.api_store import StubAuthenticator, store_over
from tests.unit.services.evaluation.cross_section.conftest import (
    ACTIVE,
    build_world,
    edge_document,
    screen,
)

PAGE = """query EdgesPage {
  edgeProblems { edgeId reason }
  edges { id status mine followed oosHidden extends compare { reason rows { kind } } }
}"""
PUBLISHED = "query PublishedEdge($id: String!) { publishedEdgeDocument(id: $id) }"


@pytest.fixture
def client(writer_client: TestClient, root: Path) -> TestClient:
    folder = root / "site" / "edges" / "drift"
    folder.mkdir(parents=True)
    (folder / "edge.toml").write_text(SITE_EDGE)
    return writer_client


def by_id(page: dict[str, list[dict[str, object]]]) -> dict[object, dict[str, object]]:
    return {e["id"]: e for e in page["edges"]}  # type: ignore[index]


def read_page(gate: Gate, c: TestClient) -> dict[object, dict[str, object]]:
    """The page after a write: not served from the cache."""
    return by_id(gate.fresh(c, PAGE))


def warm_page(gate: Gate, c: TestClient) -> dict[object, dict[str, object]]:
    """The page, proven served from the cache on its repeat."""
    return by_id(gate.warm(c, PAGE))


def test_copy_shows_the_new_edge(gate: Gate, client: TestClient, trader_client: TestClient) -> None:
    assert list(warm_page(gate, client)) == ["drift"]
    assert list(by_id(gate.warm(trader_client, PAGE))) == ["drift"]
    assert client.post("/edges/drift/copy", json={"new_id": "mine"}).status_code == 201
    page = read_page(gate, client)
    assert (page["mine"]["mine"], page["mine"]["extends"]) == (True, "drift")
    assert list(by_id(gate.warm(trader_client, PAGE))) == ["drift"]  # bob has no copy


def test_save_shows_the_new_document(gate: Gate, client: TestClient) -> None:
    assert client.post("/edges/drift/copy", json={"new_id": "mine"}).status_code == 201
    doc = {"extends": "drift", "top_k": 2}
    assert client.put("/edges/mine", json={"document": doc}).status_code == 200
    assert "top_k = 2" in gate.warm(client, PUBLISHED, id="mine")
    assert client.put("/edges/mine", json={"document": doc | {"top_k": 3}}).status_code == 200
    assert "top_k = 3" in gate.fresh(client, PUBLISHED, id="mine")


def test_delete_removes_the_edge(gate: Gate, client: TestClient) -> None:
    assert client.post("/edges/drift/copy", json={"new_id": "mine"}).status_code == 201
    assert list(warm_page(gate, client)) == ["drift", "mine"]
    assert "mine" in gate.warm(client, PUBLISHED, id="mine")
    assert client.delete("/edges/mine").status_code == 204
    assert list(read_page(gate, client)) == ["drift"]
    assert gate.fresh(client, PUBLISHED, id="mine") is None


def test_state_shows_a_status_and_a_follow(gate: Gate, client: TestClient) -> None:
    assert client.post("/edges/drift/copy", json={"new_id": "mine"}).status_code == 201
    before = warm_page(gate, client)
    assert (before["mine"]["status"], before["drift"]["followed"]) == ("researching", False)
    rejected = client.put("/edges/mine/state", json={"status": "rejected", "reason": "No edge."})
    assert rejected.status_code == 200
    assert read_page(gate, client)["mine"]["status"] == "rejected"
    gate.warm(client, PAGE)
    assert client.put("/edges/drift/state", json={"follow": True}).status_code == 200
    assert read_page(gate, client)["drift"]["followed"] is True
    gate.warm(client, PAGE)
    assert client.put("/edges/drift/state", json={"follow": False}).status_code == 200
    assert read_page(gate, client)["drift"]["followed"] is False


@pytest.fixture
def evaluating() -> Iterator[TestClient]:
    world = build_world()
    configs = MemoryConfigStore(
        {
            ("site", "selections", "active"): ACTIVE,
            ("site", "strategies", "momo"): screen(),
            ("site", "edges", "drift"): edge_document(),
            ("alice", "edges", "mine"): {"extends": "drift"},
            ("site", "settings", "users"): {
                "user": [{"id": "alice", "role": "trader"}, {"id": "ana", "role": "admin"}]
            },
        }
    )
    app = create_app(
        ApiSettings("memory://", "config"),
        store_over(world.backend, configs, UserContext("alice")),
        ondemand_edges=OnDemandEdges(world.backend, configs),
        authenticator=StubAuthenticator(UserRecord("alice", Role.TRADER)),
    )
    with TestClient(app) as test_client:
        yield test_client


def test_evaluate_shows_the_verdict_once_the_run_is_stored(
    gate: Gate, evaluating: TestClient
) -> None:
    c = evaluating
    before = warm_page(gate, c)["mine"]["compare"]
    assert before["reason"] == "You have not run this edge yet"
    started = c.post("/edges/mine/evaluate")
    assert started.status_code == 202, started.text
    deadline = time.monotonic() + 20
    while c.get(f"/jobs/{started.json()['job_id']}").json()["state"] in ("queued", "running"):
        assert time.monotonic() < deadline, "the evaluation did not finish"
        time.sleep(0.02)
    assert read_page(gate, c)["mine"]["compare"]["reason"] != before["reason"]  # a run exists
