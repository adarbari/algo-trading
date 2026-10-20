"""``Query.guideEdgeIndex``, ``guideMechanism``, ``guideEdge`` over the repo's site configs (ADR
0051), and the mechanism and edge kinds of ``guideEntries``, the Guide index's rail and a
screener's edges: the shapes the web reads; null for an unknown id; no user's edge."""

from typing import Any

from tests.apps.api.graphql.conftest import Graph

ROW = "id name thesis mechanism asset assetText side sideTerm holdingSessions holdingText "
ROW += "holdingBand status"
INDEX = f"""query I {{
  guideEdgeIndex {{
    mechanisms {{ id title question short examples count ideas statuses {{ status count }}
      edges {{ {ROW} }} }}
    filters {{ assets {{ id text count }} sides {{ id text count }} holdings {{ id text count }} }}
    setAsideTitle setAsidePurpose
    setAside {{ edge {{ id status }} why {{ text }} }}
    notBuiltTitle notBuiltPurpose
    notBuilt {{ id title mechanism verdict verdictText feasibilityText feasibilityTerm
      whyNotBuilt }}
  }}
}}"""
MECHANISM = f"""query M($id: String!) {{
  guideMechanism(id: $id) {{
    id title question short examples
    howItWorks {{ text }} whyItSurvives {{ text }} research {{ text }} realVsDecoy {{ text }}
    dont {{ text }} seeAlso stats {{ title value reading source }}
    sources {{ title url reading }} edges {{ {ROW} }}
    notBuilt {{ id mechanism verdict }}
  }}
}}"""
EDGE = f"""query E($id: String!) {{
  guideEdge(id: $id) {{
    summary {{ {ROW} }} mechanism {{ id title }}
    thesis {{ text }} otherSide {{ text segments {{ text field }} }} lasts {{ text }}
    research {{ measure figure expect haircut horizonText leg sample source terms }}
    tests {{ key title text term }} screeners {{ id name family }} fields
    failureModes {{ text }} decoys {{ text }} rejection {{ text }} capacity {{ text }}
    sources {{ title url form }} related {{ id name }} seeAlso
  }}
}}"""
ENTRIES = """query N($refs: [GuideRef!]!) {
  guideEntries(refs: $refs) {
    mechanisms { id title } edges { summary { id name } }
  }
}"""
SCREENER = "query P($id: String!) { guideScreener(id: $id) { id edges { id name status } } }"


def _data(graph: Graph, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    body = graph(query, variables)
    assert "errors" not in body, body
    data: dict[str, Any] = body["data"]
    return data


def test_the_edge_index(graph: Graph) -> None:
    index = _data(graph, INDEX)["guideEdgeIndex"]
    assert [m["id"] for m in index["mechanisms"]][:2] == ["slow_to_update", "forced_flows"]
    card = index["mechanisms"][0]
    assert card["count"] == len(card["edges"]) == sum(s["count"] for s in card["statuses"])
    assert card["question"] and card["short"] and card["examples"]
    assert {o["id"] for o in index["filters"]["assets"]} <= {"stocks", "etfs", "options"}
    assert index["setAside"] and all(s["why"]["text"] for s in index["setAside"])
    assert {s["edge"]["status"] for s in index["setAside"]} <= {"rejected", "blocked"}
    assert index["notBuiltTitle"] and index["notBuilt"]
    assert sum(m["ideas"] for m in index["mechanisms"]) == len(index["notBuilt"])
    idea = index["notBuilt"][0]
    assert idea["whyNotBuilt"] and idea["feasibilityTerm"] == "idea_feasibility"


def test_a_mechanism_page(graph: Graph) -> None:
    page = _data(graph, MECHANISM, {"id": "value_gaps"})["guideMechanism"]
    assert page["title"] and page["howItWorks"] and page["dont"]["text"]
    assert page["edges"] and all(e["mechanism"] == "value_gaps" for e in page["edges"])
    assert all(i["mechanism"] == "value_gaps" for i in page["notBuilt"]) and page["notBuilt"]
    assert page["stats"][0]["title"] and page["sources"][0]["url"].startswith("https://")


def test_an_edge_page(graph: Graph) -> None:
    page = _data(graph, EDGE, {"id": "momentum_12_1"})["guideEdge"]
    assert page["summary"]["id"] == "momentum_12_1" and page["mechanism"]["id"]
    assert page["research"]["haircut"].endswith("planning haircut")
    keys = [t["key"] for t in page["tests"]]
    assert keys[:3] == ["outcome", "horizon", "trigger"]
    assert page["screeners"][0]["id"] == "momentum_12_1" and page["fields"]
    assert page["sources"] and page["related"] and page["seeAlso"]


def test_a_page_has_no_harness_result_in_its_shape(graph: Graph) -> None:
    body = graph('{ __type(name: "GuideEdgeEntry") { fields { name } } }')["data"]["__type"][
        "fields"
    ]
    names = {f["name"] for f in body}
    assert not names & {"verdict", "winRate", "lift", "curve", "runId", "expectedSize", "notes"}


def test_unknown_ids_are_null(graph: Graph) -> None:
    assert _data(graph, MECHANISM, {"id": "nope"})["guideMechanism"] is None
    assert _data(graph, EDGE, {"id": "nope"})["guideEdge"] is None


def test_the_batched_entries_and_the_screener_backlink(graph: Graph) -> None:
    refs = [
        {"kind": "EDGE", "id": "momentum_12_1"},
        {"kind": "MECHANISM", "id": "forced_flows"},
        {"kind": "EDGE", "id": "nope"},
    ]
    found = _data(graph, ENTRIES, {"refs": refs})["guideEntries"]
    assert [e["summary"]["id"] for e in found["edges"]] == ["momentum_12_1"]
    assert [m["id"] for m in found["mechanisms"]] == ["forced_flows"]
    screener = _data(graph, SCREENER, {"id": "momentum_12_1"})["guideScreener"]
    assert "momentum_12_1" in [e["id"] for e in screener["edges"]]


def test_the_guide_index_lists_the_mechanisms(graph: Graph) -> None:
    index = _data(
        graph, "{ guideIndex { sections { id entries } mechanisms { id title count } } }"
    )["guideIndex"]
    assert index["mechanisms"][0]["id"] == "slow_to_update"
    edges = next(s for s in index["sections"] if s["id"] == "edges")
    assert edges["entries"] == len(index["mechanisms"]) + sum(
        m["count"] for m in index["mechanisms"]
    )
