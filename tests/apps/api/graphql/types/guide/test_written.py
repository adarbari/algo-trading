"""``Query.guideTerm`` and ``Query.guideStartPage`` over the repo's site configs (ADR 0051): a
glossary term with its body linked and its see-also terms, a Start here page with its sections
linked and its links titled, and both in the index; null for an unknown id."""

from tests.apps.api.graphql.conftest import Graph

ADV = "rollup.price_stats@v2.adv_usd_20d"
PAGES = """query P($term: String!, $page: String!) {
  guideTerm(id: $term) {
    entry { id term short } body { text segments { text field } } seeAlso { id term short }
  }
  guideStartPage(id: $page) {
    entry { id order title summary }
    sections { title body { text segments { field } } }
    links { kind id title }
  }
  guideIndex { startPages { id order title summary } terms { id term short } }
}"""


def test_a_term_and_a_start_page(graph: Graph) -> None:
    body = graph(PAGES, {"term": "liquidity_risk", "page": "build_a_screen"})
    assert "errors" not in body, body
    data = body["data"]
    term = data["guideTerm"]
    assert (term["entry"]["id"], term["entry"]["term"]) == ("liquidity_risk", "LIQUIDITY_RISK")
    assert "".join(s["text"] for s in term["body"]["segments"]) == term["body"]["text"]
    assert ADV in [s["field"] for s in term["body"]["segments"]]
    assert {t["id"] for t in term["seeAlso"]} >= {"on_miss", "near_miss"}
    page = data["guideStartPage"]
    assert page["entry"]["order"] == 3 and page["entry"]["title"] == "Build a screen"
    assert page["sections"] and all(s["body"]["text"] for s in page["sections"])
    assert {"kind": "field", "id": ADV, "title": ADV} in page["links"]
    index = data["guideIndex"]
    orders = [p["order"] for p in index["startPages"]]
    assert orders == list(range(1, len(orders) + 1))
    assert term["entry"] in index["terms"]


def test_unknown_ids_are_null(graph: Graph) -> None:
    body = graph(PAGES, {"term": "LIQUIDITY_RISK", "page": "Build a screen"})
    assert "errors" not in body, body
    assert body["data"]["guideTerm"] is None and body["data"]["guideStartPage"] is None
