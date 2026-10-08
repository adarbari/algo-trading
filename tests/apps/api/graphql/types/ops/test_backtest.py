"""``Query.backtests`` and ``Query.backtest`` over the golden API store: the saved runs of the
strategy configs the user sees, and one run's detail (null for anything that is not a
backtest run)."""

from fastapi.testclient import TestClient

from algotrade_api.graphql.types.ops.backtest import _public
from tests.apps.api.graphql.conftest import Graph

RUNS = "{ backtests { runId configId user status start end startedAt finishedAt metrics } }"
DETAIL = """query B($id: String!) {
  backtest(runId: $id) {
    summary { runId configId }
    configHash selection data rebalances
    equity { ts equity grossExposure }
    fills { ts instrumentId side quantity price commission multiplier }
  }
}"""


def test_backtest_list(graph: Graph, ids: dict[str, str]) -> None:
    body = graph(RUNS)
    assert "errors" not in body
    runs = body["data"]["backtests"]
    assert [r["runId"] for r in runs] == [ids["backtest"]]
    assert runs[0]["metrics"] == {"sharpe": 1.2}
    assert (runs[0]["configId"], runs[0]["user"], runs[0]["end"]) == (
        "sma_trend",
        "local",
        "2022-11-23",
    )


def test_backtest_detail(graph: Graph, ids: dict[str, str]) -> None:
    body = graph(DETAIL, {"id": ids["backtest"]})
    assert "errors" not in body
    detail = body["data"]["backtest"]
    assert detail["summary"]["runId"] == ids["backtest"]
    assert [p["equity"] for p in detail["equity"]] == [100000.0, 101000.0]
    assert detail["fills"][0]["instrumentId"] == "EQ:AAA"
    assert detail["selection"] == {"instruments": ["EQ:AAA"]}


def test_not_a_backtest_run_is_null(graph: Graph, ids: dict[str, str]) -> None:
    for run_id in ("nope", ids["nightly"], ".x"):
        body = graph(DETAIL, {"id": run_id})
        assert "errors" not in body and body["data"]["backtest"] is None


def test_the_backtests_page_reads_no_rest(client: TestClient) -> None:
    assert client.get("/backtests").status_code == 404


def test_a_traders_copy_of_a_backtest_document_has_no_tables() -> None:
    audit = {"instruments": ["EQ:AAA"], "missing_tables": ["rollups/x@v1"]}
    assert _public(None, audit) == {"instruments": ["EQ:AAA"]}
