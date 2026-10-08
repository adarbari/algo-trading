"""``Query.guideEpisode`` over the repo's site configs (ADR 0051): a reference episode by its
slug (its key) as the config holds it, cause and notes linked, the indicators whose before-line
is about it; every episode the index lists resolves; null for an unknown slug."""

from typing import Any

from tests.apps.api.graphql.conftest import Graph

EPISODE = """query E($slug: String!) {
  guideEpisode(slug: $slug) {
    episode { key name kind peak trough recovered spxDrawdown nasdaqDrawdown recession
      nberStart nberEnd knownFrom }
    cause { text segments { text field } }
    notes { text }
    indicators { key plainName label line { text } }
  }
}"""


def _episode(graph: Graph, slug: str) -> dict[str, Any] | None:
    body = graph(EPISODE, {"slug": slug})
    assert "errors" not in body, body
    found: dict[str, Any] | None = body["data"]["guideEpisode"]
    return found


def test_an_episode_page(graph: Graph) -> None:
    found = _episode(graph, "gfc_2007")
    assert found is not None
    page = {**found["episode"], **found}
    assert (page["peak"], page["trough"], page["spxDrawdown"]) == (
        "2007-10-09",
        "2009-03-09",
        -0.57,
    )
    assert page["recession"] and page["nberStart"] == "2007-12-01"
    assert page["cause"]["text"] and page["notes"]["text"]
    assert {i["label"] for i in page["indicators"]} == {"2008"}
    assert "curve_10y3m" in [i["key"] for i in page["indicators"]]


def test_every_indexed_episode_resolves_and_unknown_slugs_are_null(graph: Graph) -> None:
    body = graph("{ guideIndex { episodes { key name } } }")
    assert "errors" not in body, body
    listed = body["data"]["guideIndex"]["episodes"]
    assert listed
    for entry in listed:
        page = _episode(graph, entry["key"])
        assert page is not None and page["episode"]["name"] == entry["name"]
    assert _episode(graph, "Global financial crisis, 2007-09") is None
