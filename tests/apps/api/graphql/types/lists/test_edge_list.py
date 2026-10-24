"""``Query.edgeList`` over the golden API store (ADR 0082)."""

from algotrade.services.read.evaluation import versions
from tests.apps.api.graphql.conftest import Graph

EDGE_LIST = """query($filters: [FilterInput!], $q: String) {
  edgeList(filters: $filters, q: $q) {
    total items { id name }
    facets { total matched items { id removes unknown options { value count } } }
  }
}"""


def test_the_list_serves_counts_and_the_search_matches_the_name(graph: Graph) -> None:
    body = graph(EDGE_LIST, {})
    assert "errors" not in body, body
    found = body["data"]["edgeList"]
    assert found["total"] == len(found["items"]) == found["facets"]["total"]
    if found["items"]:
        first = found["items"][0]
        by_name = graph(EDGE_LIST, {"q": first["name"].upper()})["data"]["edgeList"]
        assert first["id"] in {i["id"] for i in by_name["items"]}


def test_a_filter_the_viewer_is_not_offered_is_refused(graph: Graph) -> None:
    body = graph(EDGE_LIST, {"filters": [{"id": "hit_rate", "min": 0.5}]})
    assert body["errors"], body


def test_the_summary_the_list_read_is_not_read_again(graph: Graph, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []
    real = versions.load_summary
    monkeypatch.setattr(versions, "load_summary", lambda ctx, e: calls.append(e.id) or real(ctx, e))
    body = graph("{ edgeList { items { id summary { verdict } } } }", {})
    assert "errors" not in body, body
    items = body["data"]["edgeList"]["items"]
    assert sorted(calls) == sorted(i["id"] for i in items)  # once per edge, not twice
