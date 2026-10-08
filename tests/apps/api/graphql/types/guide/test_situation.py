"""``Query.guideSituation`` over the repo's site configs (ADR 0051): a situation by slug with
its signs and what to do linked at catalogue names, the fields it fools and the site playbooks
deciding on them; null for an unknown slug."""

from typing import Any

from tests.apps.api.graphql.conftest import Graph

SITUATION = """query S($slug: String!) {
  guideSituation(slug: $slug) {
    slug name affects
    signs { text segments { text field } }
    do { text segments { text field } }
    playbooks { id name fields }
  }
}"""


def _situation(graph: Graph, slug: str) -> dict[str, Any] | None:
    body = graph(SITUATION, {"slug": slug})
    assert "errors" not in body, body
    found: dict[str, Any] | None = body["data"]["guideSituation"]
    return found


def test_a_situation_page(graph: Graph) -> None:
    page = _situation(graph, "pending-takeover")
    assert page is not None and page["name"] == "pending takeover"
    signs = page["signs"]
    assert "".join(s["text"] for s in signs["segments"]) == signs["text"]
    assert "feature.atr_pct" in [s["field"] for s in signs["segments"]]
    assert page["playbooks"] and all(
        set(p["fields"]) <= set(page["affects"]) and p["fields"] for p in page["playbooks"]
    )


def test_the_field_page_and_index_carry_the_slug_and_linked_prose(graph: Graph) -> None:
    query = """{ guideIndex { situations { name slug } }
      guideField(name: "rollup.momentum@v1.rsi_14") {
        readsLinked { text segments { field } } caveatsLinked { text }
        situations { slug signsLinked { text } doLinked { segments { field } } }
      } }"""
    body = graph(query)
    assert "errors" not in body, body
    slugs = {s["name"]: s["slug"] for s in body["data"]["guideIndex"]["situations"]}
    assert slugs["pending takeover"] == "pending-takeover"
    page = body["data"]["guideField"]
    assert page["readsLinked"]["text"] and page["caveatsLinked"]
    assert all(s["slug"] in slugs.values() for s in page["situations"])


def test_an_unknown_slug_is_null(graph: Graph) -> None:
    assert _situation(graph, "pending takeover") is None
