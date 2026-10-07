"""``Query.guidePlaybook`` over the repo's site configs (ADR 0051): the playbook's prose linked
at catalogue names, the latest preset version, the criteria table in file order with what each
asks, related playbooks and the situations that fool its fields; null for no such id."""

from typing import Any

from tests.apps.api.graphql.conftest import Graph

PLAYBOOK = """query P($id: String!) {
  guidePlaybook(id: $id) {
    id name family familyTitle version
    prose {
      summary { text segments { text field } }
      hit { text }
      notChecked { text }
      beforeActing { text segments { text field } }
      sources
    }
    criteria { name asks field rule mode onMiss }
    tieBreak tieBreakDescending
    related { id name reason }
    situations { slug name fields }
  }
}"""


def _playbook(graph: Graph, playbook_id: str) -> dict[str, Any] | None:
    body = graph(PLAYBOOK, {"id": playbook_id})
    assert "errors" not in body, body
    found: dict[str, Any] | None = body["data"]["guidePlaybook"]
    return found


def test_a_playbook_page(graph: Graph) -> None:
    page = _playbook(graph, "support_reversal")
    assert page is not None
    assert (page["name"], page["family"], page["familyTitle"]) == (
        "Support reversal", "reversals", "Reversals",
    )  # fmt: skip
    assert page["version"] == 2  # the latest preset version
    assert page["prose"]["summary"]["text"] and page["prose"]["sources"]
    linked = [s["field"] for c in page["prose"]["beforeActing"] for s in c["segments"]]
    assert "rollup.pivot_strength@v1.support_touches" in linked
    first = page["criteria"][0]
    assert (first["name"], first["field"], first["mode"]) == (
        "security_type", "instrument.security_type", "hard",
    )  # fmt: skip
    assert all(c["asks"] for c in page["criteria"])
    volume = next(c for c in page["criteria"] if c["name"] == "option_volume")
    assert (volume["mode"], volume["onMiss"]) == ("soft", "LIQUIDITY_RISK")
    assert page["tieBreak"] == "feature.put_support_cushion_atr"
    assert [r["id"] for r in page["related"]][:1] == ["oversold_reversal"]
    slugs = {s["slug"]: s["fields"] for s in page["situations"]}
    assert slugs["earnings-gap-inside-the-window"] == ["rollup.momentum@v1.rel_volume"]


def test_no_such_playbook_is_null(graph: Graph) -> None:
    assert _playbook(graph, "nope") is None
