"""``Query.edgeList`` over the golden API store (ADR 0082)."""

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
