"""``Query.screener``, ``ScreenerRun.results`` and ``Instrument.screenerHits`` over the golden
API store (``tests/helpers/api_store.py``): the site preset ``vrp_scanner`` ran on END (AAA
QUALIFIED, BBB WATCH, CCC PAUSED by the gate in CAUTION) and on PREVIOUS (AAA REJECT, BBB and
CCC QUALIFIED)."""

from typing import Any

from tests.apps.api.graphql.conftest import Graph

CLOSE = "rollup.price_stats@v2.close"
RESULTS = """query Results($id: String!, $decisions: [String!], $change: String, $q: String,
    $sort: String, $columns: [FeatureName!], $page: Int, $size: Int, $date: Date) {
  screener(id: $id, date: $date) {
    id criteria { id field mode } displayColumns { name field }
    latestRun {
      runId session previousSession audit paused regime coverage
      decisions { decision count }
      changes { change count }
      results(decisions: $decisions, change: $change, q: $q, sort: $sort, columns: $columns,
              page: $page, size: $size) {
        runId sort total page size
        columns { name format }
        rows unknown
        results {
          rank decision score reasons flags change previousDecision regime sizeMultiplier
          instrument { symbol name }
          criteria { id outcome value }
          columns { name value }
        }
      }
    }
    notRun { code }
  }
}"""


def results(graph: Graph, **variables: Any) -> dict[str, Any]:
    body = graph(RESULTS, {"id": "vrp_scanner", **variables})
    assert "errors" not in body, body
    return body["data"]["screener"]  # type: ignore[no-any-return]


def symbols(found: dict[str, Any]) -> list[str]:
    return [r["instrument"]["symbol"] for r in found["latestRun"]["results"]["results"]]


def test_the_run_as_a_review_table(graph: Graph) -> None:
    found = results(graph)
    assert [c["id"] for c in found["criteria"]][:3] == ["security_type", "status", "optionable"]
    assert found["displayColumns"] and found["notRun"] is None
    run = found["latestRun"]
    assert (run["session"], run["previousSession"]) == ("2022-11-23", "2022-11-22")
    assert {d["decision"]: d["count"] for d in run["decisions"]} == {
        "QUALIFIED": 1, "WATCH": 1, "PAUSED": 1
    }  # fmt: skip
    assert (run["paused"], run["regime"]) == (1, "CAUTION")
    assert run["coverage"] == run["audit"].get("coverage")
    assert run["changes"] == [{"change": "new", "count": 1}, {"change": "dropped", "count": 1}]
    page = run["results"]
    assert (page["sort"], page["total"], page["page"]) == ("rank", 3, 1)
    aaa, bbb, ccc = page["results"]
    assert (aaa["rank"], aaa["instrument"]["symbol"], aaa["decision"]) == (1, "AAA", "QUALIFIED")
    assert aaa["flags"] == ["leveraged_inverse"]
    assert aaa["columns"] == [{"name": "spread", "value": 0.05}]
    assert {c["id"]: (c["value"], c["outcome"]) for c in aaa["criteria"]}["iv30"] == (
        0.62, "PASS"
    )  # fmt: skip
    assert (bbb["reasons"], bbb["criteria"][0]["outcome"]) == ("iv rank 40 < 50", "NEAR")
    assert (ccc["decision"], ccc["regime"], ccc["sizeMultiplier"]) == ("PAUSED", "CAUTION", 0.75)
    assert ccc["reasons"] == "regime=CAUTION: vrp_scanner pauses in CAUTION"
    assert [(r["change"], r["previousDecision"]) for r in (aaa, bbb, ccc)] == [
        ("new", "REJECT"), (None, "QUALIFIED"), ("dropped", "QUALIFIED")
    ]  # fmt: skip


def test_filters_search_sort_and_page(graph: Graph) -> None:
    assert symbols(results(graph, decisions=["qualified", "watch"])) == ["AAA", "BBB"]
    assert symbols(results(graph, decisions=["paused"])) == ["CCC"]
    assert symbols(results(graph, change="dropped")) == ["CCC"]
    assert symbols(results(graph, q="bb")) == ["BBB"]
    assert symbols(results(graph, sort="-score")) == ["BBB", "AAA", "CCC"]
    assert symbols(results(graph, sort="-criterion:iv30")) == ["AAA", "BBB", "CCC"]
    second = results(graph, page=2, size=2)["latestRun"]["results"]
    assert (second["total"], [r["instrument"]["symbol"] for r in second["results"]]) == (
        3, ["CCC"]
    )  # fmt: skip


def test_catalogue_columns_are_cells_and_sortable(graph: Graph) -> None:
    page = results(graph, columns=[CLOSE], sort=f"-{CLOSE}")["latestRun"]["results"]
    assert page["columns"] == [{"name": CLOSE, "format": "CURRENCY"}]
    closes = [row[0] for row in page["rows"]]
    assert closes == sorted(closes, reverse=True) and len(closes) == 3
    assert page["unknown"] == [[None]] * 3


def test_bad_arguments_are_request_errors(graph: Graph) -> None:
    for variables, code in (
        ({"change": "gone"}, "BAD_REQUEST"),
        ({"sort": "nope"}, "UNKNOWN_FEATURE"),
        ({"columns": ["feature.no_such"]}, "UNKNOWN_FEATURE"),
    ):
        body = graph(RESULTS, {"id": "vrp_scanner", **variables})
        assert body["errors"][0]["extensions"]["code"] == code, body


def test_no_such_screener_and_a_session_with_no_run(graph: Graph) -> None:
    assert graph(RESULTS, {"id": "nope"})["data"]["screener"] is None
    old = results(graph, date="2021-01-04")
    assert (old["latestRun"], old["notRun"]) == (None, {"code": "NOT_RUN"})


def test_an_instruments_screener_hits(graph: Graph) -> None:
    query = """query Hits($key: String!) { instrument(key: $key) {
      screenerHits { screener { id name } result { decision rank change } } } }"""
    aaa = graph(query, {"key": "AAA"})["data"]["instrument"]["screenerHits"]
    assert aaa == [{"screener": {"id": "vrp_scanner", "name": "VRP"},
                    "result": {"decision": "QUALIFIED", "rank": 1, "change": "new"}}]  # fmt: skip
    assert graph(query, {"key": "CCC"})["data"]["instrument"]["screenerHits"] == []  # PAUSED


def test_track_record_is_not_run_without_a_canonical_edge_run(graph: Graph) -> None:
    """The golden store has no edge run, so a screener has no track record: NOT_RUN, not an
    error (the loader's cases are in tests/unit/services/read/evaluation)."""
    body = graph(
        """query { edges { id } edgeRuns(edgeId: "nope") { runId }
          screener(id: "vrp_scanner") {
            trackRecords { edgeId runId notRun { code kind } } } }"""
    )
    assert "errors" not in body, body
    data = body["data"]
    assert data["edges"] and data["edgeRuns"] == []  # the site's edge documents, no runs
    for entry in data["screener"]["trackRecords"]:
        assert entry["runId"] is None and entry["notRun"]["code"] == "NOT_RUN"


PICK_HISTORY = """query History($id: String!, $sessions: Int) {
  screener(id: $id) {
    pickHistory(sessions: $sessions) { session picked paused notRun { code } }
  }
}"""


def test_pick_history_is_one_entry_per_session_oldest_first(graph: Graph) -> None:
    body = graph(PICK_HISTORY, {"id": "vrp_scanner", "sessions": 3})
    assert "errors" not in body, body
    first, second, third = body["data"]["screener"]["pickHistory"]
    assert (first["session"], first["picked"], first["paused"]) == ("2022-11-21", None, None)
    assert first["notRun"] == {"code": "NOT_RUN"}  # the run's absence is an entry, not a gap
    assert (second["session"], second["picked"], second["paused"]) == ("2022-11-22", 2, 0)
    assert (third["session"], third["picked"], third["paused"]) == ("2022-11-23", 2, 1)
