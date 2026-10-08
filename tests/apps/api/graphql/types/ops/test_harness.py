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
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.main import create_app
from tests.helpers.api_store import as_user
from tests.unit.services.read.evaluation.conftest import DOCS, END, FROZEN, T, write_run

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


def test_the_lost_input_tables_are_exposed() -> None:
    backend = MemoryBackend()
    trial = {"variant": "momo", "edge_variant": "main", "horizon": 5,
             "lost_sessions": {"rollups/ibkr_iv": 3}}  # fmt: skip
    ResultWriter(backend).save_run(
        RunRecord("lost", "edge-eval:drift:site", END, T).finish(
            T, complete=True, stats={"trials": [trial]}
        )
    )
    store = ReadStore(StoreReader(backend), MemoryConfigStore(DOCS), UserContext("local"))
    app = create_app(
        ApiSettings("memory://", "config"), store, authenticator=as_user("u", Role.ADMIN)
    )
    query = '{ harnessRun(runId: "lost") { lostInputs { variant horizon table sessions } } }'
    body = TestClient(app).post("/graphql", json={"query": query}).json()
    assert body["data"]["harnessRun"]["lostInputs"] == [
        {"variant": "main/momo", "horizon": 5, "table": "rollups/ibkr_iv", "sessions": 3}
    ], body


def test_a_trader_is_refused() -> None:
    post = _graph(Role.TRADER)
    for query in (LIST, ONE):
        body = post(query)
        assert body["errors"][0]["extensions"]["code"] == "FORBIDDEN", body
