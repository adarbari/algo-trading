"""``Query.guideIndex`` over the repo's site configs (ADR 0051): the sections in the spec's
order with their entry counts, the theme groups, intents, situations, playbooks by family and
the regime indicators and episodes."""

from typing import Any

from tests.apps.api.graphql.conftest import Graph

INDEX = """{ guideIndex {
  sections { id title purpose entries }
  themeGroups { id title themes { theme fields } }
  intents { intent fields }
  situations { name fields }
  families { id title playbooks { id name } }
  indicators { key plainName }
  episodes { key name }
} }"""


def _index(graph: Graph) -> dict[str, Any]:
    body = graph(INDEX)
    assert "errors" not in body, body
    found: dict[str, Any] = body["data"]["guideIndex"]
    return found


def test_the_guide_index_in_the_spec_order(graph: Graph) -> None:
    index = _index(graph)
    assert [s["id"] for s in index["sections"]] == [
        "start", "regime", "playbooks", "fields", "situations", "glossary",
    ]  # fmt: skip
    counts = {s["id"]: s["entries"] for s in index["sections"]}
    assert counts["fields"] == sum(t["fields"] for g in index["themeGroups"] for t in g["themes"])
    assert counts["situations"] == len(index["situations"]) > 0
    assert counts["regime"] == len(index["indicators"]) + len(index["episodes"])
    assert [g["id"] for g in index["themeGroups"]] == ["tradeable", "chart", "options", "company"]
    trend = index["families"][0]
    assert (trend["title"], [p["id"] for p in trend["playbooks"]]) == (
        "Trend", ["trend_continuation", "pullback", "momentum_12_1", "size_small"],
    )  # fmt: skip
    assert index["indicators"][0]["plainName"] and index["episodes"][0]["name"]
    fields = [i["fields"] for i in index["intents"]]
    assert fields == sorted(fields, reverse=True)
