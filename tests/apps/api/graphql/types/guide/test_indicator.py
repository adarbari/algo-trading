"""``Query.guideIndicator`` over the repo's site configs (ADR 0051): a regime card by its key,
its explanation linked, its before-lines with the episode slugs they mean, how it is computed,
the field it reads and its reading list; every key the index lists resolves; null for an
unknown key."""

from typing import Any

from tests.apps.api.graphql.conftest import Graph

INDICATOR = """query I($key: String!) {
  guideIndicator(key: $key) {
    key plainName technicalName pace feature
    summary { text segments { text field } }
    whyItMatters { text } whatOnMeans { text } leadTime { text } trackRecord { text }
    before { label episode line { text segments { field } } }
    how { text url }
    sources { title url }
  }
}"""


def _indicator(graph: Graph, key: str) -> dict[str, Any] | None:
    body = graph(INDICATOR, {"key": key})
    assert "errors" not in body, body
    found: dict[str, Any] | None = body["data"]["guideIndicator"]
    return found


def test_an_indicator_page(graph: Graph) -> None:
    page = _indicator(graph, "curve_10y3m")
    assert page is not None
    assert page["feature"] == "market.regime_indicators@v1.curve_10y3m"
    assert page["pace"] == "slow" and page["summary"]["text"] and page["trackRecord"]["text"]
    assert [(b["label"], b["episode"]) for b in page["before"]] == [
        ("2008", "gfc_2007"),
        ("2020", "covid_2020"),
        ("2022", "hikes_2022"),
    ]
    assert any(p["url"] for p in page["how"]) and page["sources"]


def test_every_indexed_indicator_resolves_and_unknown_keys_are_null(graph: Graph) -> None:
    body = graph("{ guideIndex { indicators { key plainName } } }")
    assert "errors" not in body, body
    listed = body["data"]["guideIndex"]["indicators"]
    assert listed
    for entry in listed:
        page = _indicator(graph, entry["key"])
        assert page is not None and page["plainName"] == entry["plainName"]
    assert _indicator(graph, "nope") is None
