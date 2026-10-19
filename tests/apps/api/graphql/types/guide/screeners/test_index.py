"""``Query.guideScreenerIndex`` and ``guideScreenerCategory`` over the repo's site configs (ADR
0051): the lead page's texts and family cards, a family's page with its screeners as rows (what
each asks, the edges that use it); null for an unknown family."""

from typing import Any

from tests.apps.api.graphql.conftest import Graph

INDEX = """query I {
  guideScreenerIndex { what versusEdge count categories { id title purpose count } }
}"""
CATEGORY = """query C($id: String!) {
  guideScreenerCategory(id: $id) {
    id title purpose intro screeners { id name line edges { id name status } }
  }
}"""


def _data(graph: Graph, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    body = graph(query, variables)
    assert "errors" not in body, body
    data: dict[str, Any] = body["data"]
    return data


def test_the_lead_page_lists_every_family_with_its_count(graph: Graph) -> None:
    index = _data(graph, INDEX)["guideScreenerIndex"]
    assert index["what"] and index["versusEdge"]
    assert [c["id"] for c in index["categories"]][:2] == ["trend", "breakouts"]
    assert sum(c["count"] for c in index["categories"]) == index["count"]


def test_a_family_page_has_its_screeners_with_what_they_ask_and_their_edges(graph: Graph) -> None:
    page = _data(graph, CATEGORY, {"id": "breakouts"})["guideScreenerCategory"]
    assert (page["title"], page["purpose"] != "", page["intro"] != "") == ("Breakouts", True, True)
    assert [s["id"] for s in page["screeners"]][:2] == ["range_breakout", "breakout"]
    assert all(s["name"] and s["line"] for s in page["screeners"])
    assert all("status" in e for s in page["screeners"] for e in s["edges"])


def test_an_unknown_family_is_null(graph: Graph) -> None:
    assert _data(graph, CATEGORY, {"id": "nope"})["guideScreenerCategory"] is None
