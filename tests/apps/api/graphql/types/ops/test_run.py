"""``Query.{nightlyRuns,run,runItems}`` over the golden API store: the nightly runs step by
step, one run record with its failures grouped, its items; null for a run that is not there."""

from fastapi.testclient import TestClient

from tests.apps.api.graphql.conftest import Graph

NIGHTLY = """query N($limit: Int!) { nightlyRuns(limit: $limit) {
  runId session status startedAt finishedAt durationS problems
  steps { name status durationS reason error counts }
} }"""
RUN = """query R($id: String!) {
  run(runId: $id) {
    runId job session status itemsTotal itemsByStatus stats
    failures { reason count examples statuses }
  }
  runItems(runId: $id) { key code status }
}"""


def test_nightly_runs(graph: Graph) -> None:
    body = graph(NIGHTLY, {"limit": 5})
    assert "errors" not in body
    [run] = body["data"]["nightlyRuns"]
    assert (run["session"], run["status"], run["durationS"]) == ("2022-11-23", "partial", 300.0)
    steps = {s["name"]: s for s in run["steps"]}
    assert steps["bars"]["counts"] == {"rows": 11}
    assert run["problems"] == ["steps not complete: chains"]


def test_nightly_limit_is_capped(graph: Graph) -> None:
    body = graph(NIGHTLY, {"limit": 101})
    assert body["data"] is None and body["errors"][0]["extensions"]["code"] == "BAD_REQUEST"


def test_one_run_and_its_items(graph: Graph, ids: dict[str, str]) -> None:
    body = graph(RUN, {"id": ids["chains"]})
    assert "errors" not in body
    run = body["data"]["run"]
    assert run["itemsTotal"] == 3
    assert run["itemsByStatus"] == {"OK": 1, "NO_CHAIN": 1, "STALE_DATA": 1}
    assert {g["reason"] for g in run["failures"]} == {"NO_CHAIN", "STALE_DATA: chain is for <date>"}
    assert body["data"]["runItems"][2] == {
        "key": "CCC",
        "code": "STALE_DATA",
        "status": "STALE_DATA: chain is for 2022-11-21",
    }


def test_no_such_run_is_null(graph: Graph) -> None:
    for run_id in ("nope", ".hidden"):
        body = graph(RUN, {"id": run_id})
        assert "errors" not in body
        assert body["data"] == {"run": None, "runItems": None}


def test_the_admin_runs_read_no_rest(client: TestClient) -> None:
    assert client.get("/admin/runs/nightly").status_code == 404
