"""``Query.filterSet`` and ``Query.ideas(filters)`` over the golden API store (ADR 0082)."""

from tests.apps.api.graphql.conftest import Graph

FILTER_SET = """query($surface: String!) {
  filterSet(surface: $surface) {
    surface label
    filters { id label group kind guide windowUnit bins options { value label } }
    withheld { id unavailable { kind features guideTerm } }
  }
}"""
IDEAS = """query($filters: [FilterInput!], $first: Int!, $after: String) {
  ideas(first: $first, after: $after, filters: $filters) {
    total hasMore nextCursor items { instrumentId }
    facets { total matched items { id active removes unknown options { value count }
                                    bins { lo hi count } } }
  }
}"""


def test_the_definitions_of_a_surface_are_served(graph: Graph) -> None:
    body = graph(FILTER_SET, {"surface": "ideas"})
    assert "errors" not in body, body
    found = body["data"]["filterSet"]
    by_id = {f["id"]: f for f in found["filters"]}
    assert found["surface"] == "ideas" and {"decision", "dollar_volume", "earnings"} <= set(by_id)
    assert by_id["dollar_volume"]["kind"] == "RANGE" and by_id["dollar_volume"]["bins"]
    assert by_id["earnings"]["windowUnit"] == "SESSIONS"
    assert {o["value"] for o in by_id["decision"]["options"]} >= {"QUALIFIED", "WATCH"}


def test_an_unknown_surface_is_an_error_not_an_empty_set(graph: Graph) -> None:
    body = graph(FILTER_SET, {"surface": "nope"})
    assert body["errors"] and body["data"]["filterSet"] is None


def test_ideas_take_filters_and_carry_facets(graph: Graph) -> None:
    body = graph(IDEAS, {"first": 10, "filters": []})
    assert "errors" not in body, body
    everything = body["data"]["ideas"]
    assert everything["facets"]["total"] == everything["facets"]["matched"] == everything["total"]
    narrowed = graph(
        IDEAS, {"first": 10, "filters": [{"id": "decision", "values": ["NOPE_DECISION"]}]}
    )
    assert "errors" not in narrowed, narrowed
    ideas = narrowed["data"]["ideas"]
    assert (ideas["total"], ideas["items"], ideas["hasMore"]) == (0, [], False)
    assert ideas["facets"]["total"] == everything["total"] and ideas["facets"]["matched"] == 0
    [decision] = [f for f in ideas["facets"]["items"] if f["id"] == "decision"]
    assert decision["active"] and decision["removes"] == everything["total"]


def test_a_filter_that_is_not_offered_is_refused(graph: Graph) -> None:
    body = graph(IDEAS, {"first": 10, "filters": [{"id": "not_a_filter", "values": ["x"]}]})
    assert body["errors"][0]["extensions"]["code"] == "FORBIDDEN"


def test_a_cursor_is_only_good_for_its_filters(graph: Graph) -> None:
    first = graph(IDEAS, {"first": 1, "filters": []})["data"]["ideas"]
    if first["nextCursor"] is None:  # the golden store holds one idea: nothing to page
        return
    body = graph(
        IDEAS,
        {
            "first": 1,
            "after": first["nextCursor"],
            "filters": [{"id": "decision", "values": ["QUALIFIED"]}],
        },
    )
    assert body["errors"][0]["extensions"]["code"] == "BAD_REQUEST"
