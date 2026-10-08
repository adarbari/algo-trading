"""``Query.harnessRuns`` / ``harnessRun``: an admin reads the evaluation runs and one run's rows,
a trader is refused (ADR 0040)."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from algotrade.config.site.users import Role
from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.main import create_app
from tests.helpers.api_store import as_user
from tests.unit.services.read.evaluation.conftest import DOCS, FROZEN, write_run

LIST = """{ harnessRuns(limit: 5) { runId edgeId user status exploratory splitFrom variants
  horizons sessions unclosed excludedCoverage scoreCoverage noEntryBar trials knowledgeTs } }"""
ONE = """{ harnessRun(runId: "r1") { runId rows { variant sliceKind hitRate } } }"""


def _graph(role: Role) -> Callable[[str], dict[str, Any]]:
    backend = MemoryBackend()
    write_run(backend, "r1", FROZEN, 0.5)
    store = ReadStore(StoreReader(backend), MemoryConfigStore(DOCS), UserContext("local"))
    app = create_app(ApiSettings("memory://", "config"), store, authenticator=as_user("u", role))
    client = TestClient(app)

    def post(query: str) -> dict[str, Any]:
        body: dict[str, Any] = client.post("/graphql", json={"query": query}).json()
        return body

    return post


def test_an_admin_reads_the_runs_and_one_runs_rows() -> None:
    post = _graph(Role.ADMIN)
    body = post(LIST)
    assert "errors" not in body, body
    [run] = body["data"]["harnessRuns"]
    assert (run["runId"], run["edgeId"], run["user"], run["exploratory"]) == (
        "r1", "drift", "site", False,
    )  # fmt: skip
    assert run["sessions"] is None and run["splitFrom"] == FROZEN.isoformat()
    one = post(ONE)["data"]["harnessRun"]
    assert {r["sliceKind"] for r in one["rows"]} == {"all", "frozen"}


def test_a_trader_is_refused() -> None:
    post = _graph(Role.TRADER)
    for query in (LIST, ONE):
        body = post(query)
        assert body["errors"][0]["extensions"]["code"] == "FORBIDDEN", body
