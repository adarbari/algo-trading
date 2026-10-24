"""``Query.filterSet`` and ``Query.ideas(filters)`` over the golden API store (ADR 0082)."""

from tests.apps.api.graphql.conftest import Graph

FILTER_SET = """query($surface: String!) {
  filterSet(surface: $surface) {
    surface label
    filters { id label group kind guide windowUnit unit bins options { value label } }
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
    assert by_id["dollar_volume_pct_universe"]["unit"] == "PERCENT"
    assert by_id["dollar_volume"]["unit"] is None
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


FEATURE = "rollup.volume@v1.dollar_volume"
FEATURE_ID = f"feature:{FEATURE}"
WITH_FEATURES = """query($surface: String!, $names: [String!]) {
  filterSet(surface: $surface, withFeatures: $names) {
    searchable filters { id group kind guide bins }
    withheld { id }
  }
  filterFeatures(surface: $surface) { name label kind guide synonyms }
}"""


def test_a_surface_with_catalogue_fields_is_searchable_and_lists_the_features(
    graph: Graph,
) -> None:
    body = graph(WITH_FEATURES, {"surface": "ideas"})
    assert "errors" not in body, body
    assert body["data"]["filterSet"]["searchable"] is True
    found = {f["name"]: f for f in body["data"]["filterFeatures"]}
    assert found[FEATURE]["kind"] == "RANGE" and found[FEATURE]["guide"] == f"field:{FEATURE}"


def test_a_surface_of_its_own_columns_takes_no_features(graph: Graph) -> None:
    body = graph(WITH_FEATURES, {"surface": "screeners"})
    assert body["data"]["filterSet"]["searchable"] is False
    assert body["data"]["filterFeatures"] == []


def test_a_requested_feature_is_served_as_a_filter_of_the_more_group(graph: Graph) -> None:
    body = graph(WITH_FEATURES, {"surface": "ideas", "names": [FEATURE]})
    [made] = [f for f in body["data"]["filterSet"]["filters"] if f["id"] == FEATURE_ID]
    assert (made["group"], made["kind"], made["guide"]) == ("MORE", "RANGE", f"field:{FEATURE}")
    plain = graph(WITH_FEATURES, {"surface": "ideas"})
    assert FEATURE_ID not in {f["id"] for f in plain["data"]["filterSet"]["filters"]}


def test_ideas_filter_on_a_feature_made_on_the_fly_and_count_it(graph: Graph) -> None:
    everything = graph(IDEAS, {"first": 10, "filters": []})["data"]["ideas"]
    body = graph(IDEAS, {"first": 10, "filters": [{"id": FEATURE_ID, "values": [], "min": 1e30}]})
    assert "errors" not in body, body
    ideas = body["data"]["ideas"]
    assert (ideas["total"], ideas["items"]) == (0, [])
    [made] = [f for f in ideas["facets"]["items"] if f["id"] == FEATURE_ID]
    assert made["active"] and made["removes"] == everything["total"]


def test_a_feature_filter_for_an_unknown_field_is_refused(graph: Graph) -> None:
    body = graph(
        IDEAS, {"first": 10, "filters": [{"id": "feature:rollup.nope@v1.x", "values": []}]}
    )
    assert body["errors"][0]["extensions"]["code"] == "FORBIDDEN"
