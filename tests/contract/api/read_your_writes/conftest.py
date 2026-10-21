"""The gate's harness: the real app with its real response cache over the authoring fixtures,
a counter of the response cache's hits, and two modes of every test:
``with_epoch`` (the app as served) and ``durable_only`` (the process-local ``WriteEpoch`` never
moves, so only the durable config or runs generation can invalidate an answer)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from algotrade_api import main
from algotrade_api.graphql.response_cache import ResponseCache
from tests.apps.api.routes.authoring.conftest import root, trader_client, writer_client

__all__ = ["Gate", "gate", "root", "trader_client", "writer_client"]


EPOCHS: list[Any] = []


class _NoCount:
    """``CountWrites`` that counts nothing (the ``durable_only`` mode)."""

    def __init__(self, app: Any, epoch: Any) -> None:
        self.app = app
        EPOCHS.append(epoch)  # the app's WriteEpoch, which nothing moves in this mode

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        await self.app(scope, receive, send)


class Gate:
    """Reads a GraphQL operation through the real cache and tells a hit from a miss."""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.hits = 0  # fresh entries the response cache served

    def read(self, client: TestClient, document: str, **variables: Any) -> Any:
        """The operation's data: its one root field's value, or all of them (a dict)."""
        body = client.post("/graphql", json={"query": document, "variables": variables}).json()
        assert "errors" not in body, body
        data = body["data"]
        return next(iter(data.values())) if len(data) == 1 else data

    def warm(self, client: TestClient, document: str, **variables: Any) -> Any:
        """Read twice and prove the second answer came from the response cache."""
        first = self.read(client, document, **variables)
        before = self.hits
        again = self.read(client, document, **variables)
        assert self.hits == before + 1, "the repeat was not served from the response cache"
        assert again == first
        return first

    def fresh(self, client: TestClient, document: str, **variables: Any) -> Any:
        """Read once after a write: the earlier cached answer must not be served."""
        before = self.hits
        data = self.read(client, document, **variables)
        if self.mode == "durable_only":
            assert EPOCHS and all(e.value == 0 for e in EPOCHS), "the write epoch moved"
        assert self.hits == before, "the write left the earlier cached answer reachable"
        return data


@pytest.fixture(params=["with_epoch", "durable_only"], autouse=True)
def gate(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Gate:
    state = Gate(request.param)
    EPOCHS.clear()
    real_get = ResponseCache.get

    def counting(self: ResponseCache, key: str) -> bytes | None:
        found = real_get(self, key)
        state.hits += found is not None
        return found

    monkeypatch.setattr(ResponseCache, "get", counting)
    if request.param == "durable_only":
        monkeypatch.setattr(main, "CountWrites", _NoCount)
    return state
