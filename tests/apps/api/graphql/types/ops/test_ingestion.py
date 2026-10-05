"""``Query.{completeness,ingestionCell}`` over the golden API store: the grid of datasets x a
window of sessions, one cell's drill-down, null for a dataset the grid does not list."""

from tests.apps.api.graphql.conftest import Graph

GRID = """query G($sessions: Int!) { completeness(sessions: $sessions) {
  sessions datasets lastClosed
  cells { dataset session status present expected basis runIds }
} }"""
CELL = """query C($dataset: String!, $date: Date!) { ingestionCell(dataset: $dataset, date: $date) {
  job
  cell { dataset session status present expected }
  groups { reason count examples }
  runs { runId job status }
} }"""


def test_the_grid(graph: Graph) -> None:
    body = graph(GRID, {"sessions": 3})
    assert "errors" not in body
    grid = body["data"]["completeness"]
    assert grid["sessions"] == ["2022-11-21", "2022-11-22", "2022-11-23"]
    assert grid["lastClosed"] > "2022-11-23"  # the golden store is long stale
    cells = {(c["dataset"], c["session"]): c for c in grid["cells"]}
    bars = cells[("bars/1d", "2022-11-23")]
    assert (bars["status"], bars["present"], bars["expected"]) == ("COMPLETE", 11, 11)


def test_the_window_is_capped(graph: Graph) -> None:
    body = graph(GRID, {"sessions": 61})
    assert body["errors"][0]["extensions"]["code"] == "BAD_REQUEST"


def test_one_cell(graph: Graph) -> None:
    body = graph(CELL, {"dataset": "chains/option_quotes", "date": "2022-11-23"})
    assert "errors" not in body
    cell = body["data"]["ingestionCell"]
    assert (cell["job"], cell["cell"]["status"], cell["groups"]) == ("option_chains", "PARTIAL", [])
    assert cell["runs"][-1]["job"] == "option_chains"


def test_an_unlisted_dataset_is_null(graph: Graph) -> None:
    body = graph(CELL, {"dataset": "nope", "date": "2022-11-23"})
    assert "errors" not in body and body["data"]["ingestionCell"] is None
