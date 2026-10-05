"""``Query.screener``, ``ScreenerRun.results`` and ``Instrument.screenerHits`` over the golden
API store (``tests/helpers/api_store.py``): the site preset ``vrp_scanner`` ran on END (AAA
QUALIFIED, BBB WATCH, CCC REJECT) and on PREVIOUS (AAA REJECT, BBB and CCC QUALIFIED)."""

from typing import Any

from tests.apps.api.graphql.conftest import Graph

CLOSE = "rollup.price_stats@v2.close"
RESULTS = """query Results($id: String!, $decisions: [String!], $change: String, $q: String,
    $sort: String, $columns: [FeatureName!], $page: Int, $size: Int, $date: Date) {
  screener(id: $id, date: $date) {
    id criteria { id field mode } displayColumns { name field }
    latestRun {
      runId session previousSession audit
      decisions { decision count }
      changes { change count }
      results(decisions: $decisions, change: $change, q: $q, sort: $sort, columns: $columns,
              page: $page, size: $size) {
        runId sort total page size missing
        columns { name format }
        rows unknown
        results {
          rank decision score reasons flags change previousDecision
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
        "QUALIFIED": 1, "WATCH": 1, "REJECT": 1
    }  # fmt: skip
    assert run["changes"] == [{"change": "new", "count": 1}, {"change": "dropped", "count": 1}]
    page = run["results"]
    assert (page["sort"], page["total"], page["page"], page["missing"]) == ("rank", 3, 1, [])
    aaa, bbb, ccc = page["results"]
    assert (aaa["rank"], aaa["instrument"]["symbol"], aaa["decision"]) == (1, "AAA", "QUALIFIED")
    assert aaa["flags"] == ["leveraged_inverse"]
    assert aaa["columns"] == [{"name": "spread", "value": 0.05}]
    assert {c["id"]: (c["value"], c["outcome"]) for c in aaa["criteria"]}["iv30"] == (
        0.62, "PASS"
    )  # fmt: skip
    assert (bbb["reasons"], bbb["criteria"][0]["outcome"]) == ("iv rank 40 < 50", "NEAR")
    assert [(r["change"], r["previousDecision"]) for r in (aaa, bbb, ccc)] == [
        ("new", "REJECT"), (None, "QUALIFIED"), ("dropped", "QUALIFIED")
    ]  # fmt: skip


def test_filters_search_sort_and_page(graph: Graph) -> None:
    assert symbols(results(graph, decisions=["qualified", "watch"])) == ["AAA", "BBB"]
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
    assert graph(query, {"key": "CCC"})["data"]["instrument"]["screenerHits"] == []  # REJECT
