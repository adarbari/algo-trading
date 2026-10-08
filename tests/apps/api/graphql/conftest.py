"""``graph(query, variables)``: POST a GraphQL operation to the API over the golden API
store (``tests/apps/api/conftest.py``) and return the JSON body (always HTTP 200); ``ctx``:
the read context of that store's latest session."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from algotrade.services.read.context import ReadContext, open_context
from algotrade_api.deps import ReadStore

Graph = Callable[..., dict[str, Any]]

FACTS = """query Facts($key: String!, $names: [FeatureName!]!, $date: Date) {
  session(date: $date) { date isLatest referenceSnapshot preSnapshot unavailable { kind } }
  instrument(key: $key, date: $date) {
    instrumentId symbol name securityType assetClass exchange isEtf description
    referenceSnapshot
    features(names: $names) { name value unknown { code kind } info { format unit } }
  }
}"""


@pytest.fixture(scope="session")
def graph(client: TestClient) -> Graph:
    def post(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        response = client.post("/graphql", json={"query": query, "variables": variables or {}})
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    return post


@pytest.fixture(scope="session")
def ctx(api_golden: tuple[ReadStore, dict[str, str]]) -> ReadContext:
    store = api_golden[0]
    return open_context(store.reader, store.configs, store.user)
