"""``Query.guideSearch`` over the repo's site configs (ADR 0051): results grouped by kind, the
exact name first, at most ``limit`` per kind; the query length and the limit are capped."""

from typing import Any

from tests.apps.api.graphql.conftest import Graph

SEARCH = """query S($q: String!, $limit: Int) {
  guideSearch(q: $q, limit: $limit) { query groups { kind hits { kind id title snippet } } }
}"""


def _search(graph: Graph, q: str, limit: int = 5) -> dict[str, Any]:
    return graph(SEARCH, {"q": q, "limit": limit})


def test_grouped_results_exact_name_first(graph: Graph) -> None:
    body = _search(graph, "near miss", 2)
    assert "errors" not in body, body
    found = body["data"]["guideSearch"]
    assert found["query"] == "near miss"
    first = found["groups"][0]
    assert first["kind"] == "term" and first["hits"][0]["id"] == "near_miss"
    for group in found["groups"]:
        assert 0 < len(group["hits"]) <= 2
        assert all(h["kind"] == group["kind"] and h["title"] for h in group["hits"])


def test_a_blank_query_finds_nothing(graph: Graph) -> None:
    body = _search(graph, "  ")
    assert "errors" not in body, body
    assert body["data"]["guideSearch"]["groups"] == []


def test_the_limits_are_capped(graph: Graph) -> None:
    assert "limit: at most 50" in str(_search(graph, "rsi", 51)["errors"])
    assert "q: at most 200" in str(_search(graph, "x" * 201)["errors"])
