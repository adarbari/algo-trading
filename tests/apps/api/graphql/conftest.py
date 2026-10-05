"""``graph(query, variables)``: POST a GraphQL operation to the API over the golden explore
store (``tests/apps/api/conftest.py``) and return the JSON body (always HTTP 200); ``ctx``:
the read context of that store's latest session."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from algotrade.services.explore.store import ReadStore
from algotrade.services.read.context import ReadContext, open_context

Graph = Callable[..., dict[str, Any]]

FACTS = """query Facts($key: String!, $names: [FeatureName!]!, $date: Date) {
  session(date: $date) { date isLatest missing referenceSnapshot preSnapshot }
  instrument(key: $key, date: $date) {
    instrumentId symbol name securityType assetClass exchange isEtf description
    referenceSnapshot
    features(names: $names) { name value unknown { code detail } info { format unit } }
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
def ctx(explore: tuple[ReadStore, dict[str, str]]) -> ReadContext:
    store = explore[0]
    return open_context(store.reader, store.configs, store.user)
