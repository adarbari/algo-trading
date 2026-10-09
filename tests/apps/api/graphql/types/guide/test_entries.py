"""``Query.guideEntries`` over the repo's site configs (ADR 0051): one read for the entries a
page's help buttons ask for, equal to the single-entry fields, a ref with no entry left out,
repeated refs read once, and more than 100 refs refused."""

from tests.apps.api.graphql.conftest import Graph

ENTRIES = """query E($refs: [GuideRef!]!) {
  guideEntries(refs: $refs) {
    indicators { key plainName }
    episodes { episode { key name } }
    terms { entry { id term } }
    startPages { entry { id title } }
  }
}"""
SINGLE = """query S($key: String!, $slug: String!, $term: String!, $page: String!) {
  guideIndicator(key: $key) { key plainName }
  guideEpisode(slug: $slug) { episode { key name } }
  guideTerm(id: $term) { entry { id term } }
  guideStartPage(id: $page) { entry { id title } }
}"""


def test_a_batch_equals_the_single_entry_reads(graph: Graph) -> None:
    refs = [
        {"kind": "INDICATOR", "id": "curve_10y3m"},
        {"kind": "EPISODE", "id": "gfc_2007"},
        {"kind": "TERM", "id": "liquidity_risk"},
        {"kind": "START", "id": "build_a_screen"},
    ]
    batch = graph(ENTRIES, {"refs": refs})
    ids = {"key": "curve_10y3m", "slug": "gfc_2007", "term": "liquidity_risk"}
    single = graph(SINGLE, {**ids, "page": "build_a_screen"})
    assert "errors" not in batch and "errors" not in single, (batch, single)
    got = batch["data"]["guideEntries"]
    want = single["data"]
    assert got["indicators"] == [want["guideIndicator"]]
    assert got["episodes"] == [want["guideEpisode"]]
    assert got["terms"] == [want["guideTerm"]]
    assert got["startPages"] == [want["guideStartPage"]]


def test_unknown_refs_are_left_out_and_repeats_read_once(graph: Graph) -> None:
    refs = [
        {"kind": "INDICATOR", "id": "nope"},
        {"kind": "INDICATOR", "id": "curve_10y3m"},
        {"kind": "INDICATOR", "id": "curve_10y3m"},
        {"kind": "EPISODE", "id": "nope"},
    ]
    body = graph(ENTRIES, {"refs": refs})
    assert "errors" not in body, body
    got = body["data"]["guideEntries"]
    assert [i["key"] for i in got["indicators"]] == ["curve_10y3m"]
    assert got["episodes"] == got["terms"] == got["startPages"] == []


def test_a_batch_over_the_cap_is_refused(graph: Graph) -> None:
    refs = [{"kind": "TERM", "id": f"t{i}"} for i in range(101)]
    body = graph(ENTRIES, {"refs": refs})
    assert "errors" in body
