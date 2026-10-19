"""``Query.guideScreener`` over the repo's site configs (ADR 0051): the screener's prose linked
at catalogue names, the latest preset version, the criteria table in file order with what each
asks, related screeners and the situations that fool its fields; null for no such id."""

from typing import Any

from tests.apps.api.graphql.conftest import Graph

SCREENER = """query P($id: String!) {
  guideScreener(id: $id) {
    id name family familyTitle version
    prose {
      summary { text segments { text field source } }
      hit { text }
      notChecked { text }
      beforeActing { text segments { text field source } }
      sources { title url note }
    }
    criteria { name asks field rule mode onMiss }
    tieBreak tieBreakDescending
    related { id name reason }
    situations { slug name fields }
  }
}"""


def _screener(graph: Graph, screener_id: str) -> dict[str, Any] | None:
    body = graph(SCREENER, {"id": screener_id})
    assert "errors" not in body, body
    found: dict[str, Any] | None = body["data"]["guideScreener"]
    return found


def test_a_screener_page(graph: Graph) -> None:
    page = _screener(graph, "support_reversal")
    assert page is not None
    assert (page["name"], page["family"], page["familyTitle"]) == (
        "Support reversal", "reversals", "Reversals",
    )  # fmt: skip
    assert page["version"] == 2  # the latest preset version
    assert page["prose"]["summary"]["text"] and page["prose"]["sources"]
    sources = page["prose"]["sources"]
    assert all(src["title"] and src["note"] for src in sources)
    assert all(src["url"] is None or src["url"].startswith("https://") for src in sources)
    # A marker is its own segment naming a source of the page, and the segments join to the text.
    prose = [page["prose"]["summary"], page["prose"]["hit"], *page["prose"]["beforeActing"]]
    cited = {
        seg["source"] for p in prose for seg in p.get("segments", []) if seg["source"] is not None
    }
    assert cited and cited <= set(range(1, len(sources) + 1))
    assert "[^" not in "".join(
        seg["text"] for seg in page["prose"]["summary"]["segments"] if seg["source"] is None
    )
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


def test_no_such_screener_is_null(graph: Graph) -> None:
    assert _screener(graph, "nope") is None
