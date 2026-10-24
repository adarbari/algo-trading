"""``Query.screenerRuns`` / ``screenerRun``: an admin reads the screener runs of every user and
one run's frozen changes, a trader is refused (ADR 0040)."""

from collections.abc import Callable
from datetime import timedelta
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
from tests.unit.services.read.evaluation.conftest import DOCS
from tests.unit.services.read.ops.admin_runs.test_screener_runs import DAY, GOOD, T, _freeze

LIST = """{ screenerRuns(limit: 5, user: "site") { runId configId owner session status
  knowledgeTs configVersion configHash decisions { decision count } picked paused regime
  coverage missingTables missingOptionalTables unavailable { kind } } }"""
ALL = "{ screenerRuns { runId owner } }"
ONE = """{ screenerRun(runId: "r1") { runId changes { picked previousRunId newPicks dropped } } }"""
NO_ROW = """{ screenerRun(runId: "r2") { runId decisions { count } changes { picked } } }"""


def _graph(role: Role) -> Callable[[str], dict[str, Any]]:
    backend = MemoryBackend()
    w = ResultWriter(backend)
    w.save_run(RunRecord("r1", "screen-momo-site", DAY, T).finish(T, stats=GOOD))
    when = T + timedelta(minutes=5)
    w.save_run(RunRecord("r2", "screen-momo-local", DAY, when))  # a user's, still running
    _freeze(backend, "r1")
    store = ReadStore(StoreReader(backend), MemoryConfigStore(DOCS), UserContext("local"))
    app = create_app(ApiSettings("memory://", "config"), store, authenticator=as_user("u", role))
    client = TestClient(app)

    def post(query: str) -> dict[str, Any]:
        body: dict[str, Any] = client.post("/graphql", json={"query": query}).json()
        return body

    return post


def test_an_admin_reads_the_runs_and_one_runs_changes() -> None:
    post = _graph(Role.ADMIN)
    body = post(LIST)
    assert "errors" not in body, body
    [run] = body["data"]["screenerRuns"]
    assert (run["runId"], run["configId"], run["owner"], run["status"]) == (
        "r1", "momo", "site", "complete",
    )  # fmt: skip
    assert (run["picked"], run["paused"], run["regime"], run["configVersion"]) == (4, 2, "CALM", 3)
    assert run["decisions"][0] == {"decision": "REJECT", "count": 9}
    assert run["missingTables"] == ["rollups/ibkr_iv"] and len(run["unavailable"]) == 2
    one = post(ONE)["data"]["screenerRun"]
    assert one["changes"] == {"picked": 4, "previousRunId": "prev", "newPicks": 1, "dropped": 3}


def test_the_admin_sees_a_users_run_that_never_finished() -> None:
    post = _graph(Role.ADMIN)
    everyone = post(ALL)["data"]["screenerRuns"]
    assert [(r["runId"], r["owner"]) for r in everyone] == [("r2", "local"), ("r1", "site")]
    live = post(NO_ROW)["data"]["screenerRun"]
    assert live == {"runId": "r2", "decisions": None, "changes": None}


def test_a_trader_is_refused() -> None:
    post = _graph(Role.TRADER)
    for query in (LIST, ONE):
        body = post(query)
        assert body["errors"][0]["extensions"]["code"] == "FORBIDDEN", body
