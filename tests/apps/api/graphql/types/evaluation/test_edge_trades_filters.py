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


def test_facets_asked_for_through_a_fragment_are_served_as_when_selected_directly(
    graph: Graph,
) -> None:
    edge = first_edge(graph)
    direct = graph(
        "query($id: String!) { edgeTrades(edgeId: $id, period: null) { unknown { kind } "
        "facets { total } } }",
        {"id": edge},
    )["data"]["edgeTrades"]
    spread = "fragment F on EdgeTradePage { facets { total } }"
    for body in (
        "query($id: String!) { edgeTrades(edgeId: $id, period: null) { unknown { kind } ...F } } "
        + spread,
        "query($id: String!) { edgeTrades(edgeId: $id, period: null) { unknown { kind } "
        "... on EdgeTradePage { facets { total } } } }",
    ):
        found = graph(body, {"id": edge})
        assert "errors" not in found, found
        assert found["data"]["edgeTrades"] == direct
