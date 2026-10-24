"""``Query.edgeTrades(filters)`` over the golden API store (ADR 0082)."""

from tests.apps.api.graphql.conftest import Graph

TRADES = """query($id: String!, $filters: [FilterInput!], $period: TradePeriod) {
  edgeTrades(edgeId: $id, filters: $filters, period: $period) {
    total unknown { kind } rows { instrumentId status source }
    facets { total matched items { id unknown options { value count } bins { count } } }
  }
}"""


def first_edge(graph: Graph) -> str:
    return graph("{ edges { id } }", {})["data"]["edges"][0]["id"]


def test_facets_are_served_only_when_asked_for(graph: Graph) -> None:
    edge = first_edge(graph)
    plain = graph("query($id: String!) { edgeTrades(edgeId: $id) { total } }", {"id": edge})
    assert "errors" not in plain, plain
    counted = graph(TRADES, {"id": edge, "period": None})
    assert "errors" not in counted, counted
    found = counted["data"]["edgeTrades"]
    if found["unknown"] is None:
        assert found["facets"]["total"] >= found["total"] == found["facets"]["matched"]


def test_a_filter_the_viewer_is_not_offered_is_refused(graph: Graph) -> None:
    body = graph(TRADES, {"id": first_edge(graph), "filters": [{"id": "nope", "values": ["x"]}]})
    assert "not offered" in str(body["errors"]), body
