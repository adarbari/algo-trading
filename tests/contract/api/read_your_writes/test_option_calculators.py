"""The option calculators persist nothing (plan V11): a POST through each leaves every cached
GraphQL answer valid, so the next read is still served from the response cache, unchanged."""

from datetime import date

from fastapi.testclient import TestClient

from tests.contract.api.read_your_writes.conftest import Gate

VIEW = """query TableView($scope: String!, $name: String) {
  view(scope: $scope, name: $name) { scope saved columns sort decisions names }
}"""
SCOPE = "screener:vrp"
EXPIRY = date(2030, 1, 18).isoformat()  # any expiry: the calculator only reads


def _stores_nothing(gate: Gate, client: TestClient, path: str, body: dict[str, object]) -> None:
    before = gate.warm(client, VIEW, scope=SCOPE, name=None)
    assert client.post(path, json=body).status_code in (200, 404)  # 404: no such ticker here
    hits = gate.hits
    assert gate.read(client, VIEW, scope=SCOPE, name=None) == before
    assert gate.hits == hits + 1, "the calculator invalidated a cached answer"


def test_roll_stores_nothing(gate: Gate, writer_client: TestClient) -> None:
    body = {"key": "AAA", "strike": 95.0, "expiry": EXPIRY, "sold_at": 1.0}
    _stores_nothing(gate, writer_client, "/preview/options/roll", body)


def test_calls_stores_nothing(gate: Gate, writer_client: TestClient) -> None:
    body = {"key": "AAA", "shares": 200, "price": 98.0}
    _stores_nothing(gate, writer_client, "/preview/options/calls", body)


def test_margin_stores_nothing(gate: Gate, writer_client: TestClient) -> None:
    body = {"key": "AAA", "strike": 95.0, "expiry": EXPIRY, "contracts": 5}
    _stores_nothing(gate, writer_client, "/preview/options/margin", body)
