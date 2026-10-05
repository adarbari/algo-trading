"""``Query.catalogue`` and ``Query.distribution`` over the golden API store: the caller's
catalogue (site plus their own features) and a feature across instruments for exactly the
session (UNKNOWN when it is not stored for it, never an older partition)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.apps.api.graphql.conftest import Graph
from tests.helpers.api_store import END, PREVIOUS

CATALOGUE = """{ catalogue { name kind source dtype format version group key inputs unit
  categories scope owner licence nullMeaning } }"""
DISTRIBUTION = """query D($name: FeatureName!, $date: Date) {
  distribution(name: $name, date: $date) {
    name session count nulls info { dtype format }
    quantiles { q value } histogram { lo hi count } categories { value count }
    unknown { code detail }
  }
}"""


def _post(client: TestClient, query: str, variables: dict[str, Any] | None = None) -> Any:
    body = client.post("/graphql", json={"query": query, "variables": variables or {}}).json()
    return body


def _distribution(graph: Graph, name: str, date: str | None = None) -> dict[str, Any]:
    body = graph(DISTRIBUTION, {"name": name, "date": date})
    assert "errors" not in body, body
    found: dict[str, Any] = body["data"]["distribution"]
    return found


def test_catalogue_lists_instrument_and_rollup_fields(graph: Graph) -> None:
    body = graph(CATALOGUE)
    assert "errors" not in body
    catalogue = {f["name"]: f for f in body["data"]["catalogue"]}
    hv20 = catalogue["rollup.price_stats@v2.hv20"]
    assert (hv20["dtype"], hv20["version"], hv20["group"], hv20["key"]) == (
        "float32", 2, "price_stats@v2", "price_stats.hv20@v2",
    )  # fmt: skip
    assert hv20["kind"] != "instrument" and hv20["unit"] and hv20["nullMeaning"]
    assert hv20["inputs"] and hv20["format"] == "PERCENT"
    assert catalogue["instrument.sector"]["source"] == "instruments/company"
    label = catalogue["feature.liquidity_class"]
    assert (label["kind"], label["source"], label["key"], label["group"]) == (
        "label", "expression", "liquidity_class@v1", None,
    )  # fmt: skip
    assert label["categories"] == ["HIGH", "MEDIUM", "LOW", "UNKNOWN"] and label["inputs"]
    assert catalogue["feature.div_yield"]["source"] == "rollups/instrument/div_yield@v1"
    assert hv20["licence"] == "open" and catalogue["instrument.sector"]["licence"] == "open"


def test_catalogue_is_the_callers_site_plus_their_own_features(
    graph: Graph, user_client: Callable[[str], TestClient]
) -> None:
    site = {f["name"]: f for f in graph(CATALOGUE)["data"]["catalogue"]}
    label = site["feature.liquidity_class"]
    assert (label["scope"], label["owner"]) == ("site", None)
    assert "feature.hv20_pct" not in site
    alice = {f["name"]: f for f in _post(user_client("alice"), CATALOGUE)["data"]["catalogue"]}
    mine = alice["feature.hv20_pct"]
    assert (mine["scope"], mine["owner"], mine["source"], mine["inputs"]) == (
        "user", "alice", "expression", ["price_stats.hv20@v2"],
    )  # fmt: skip
    assert set(alice) - set(site) == {"feature.hv20_pct"}
    bob = user_client("bob")
    assert "feature.hv20_pct" not in {f["name"] for f in _post(bob, CATALOGUE)["data"]["catalogue"]}
    refused = _post(bob, DISTRIBUTION, {"name": "feature.hv20_pct"})
    assert refused["errors"][0]["extensions"]["code"] == "UNKNOWN_FEATURE"
    spread = _post(user_client("alice"), DISTRIBUTION, {"name": "feature.hv20_pct"})
    found = spread["data"]["distribution"]
    assert (found["count"], found["nulls"]) == (4, 1)


def test_numeric_distribution_for_exactly_the_session(graph: Graph) -> None:
    body = _distribution(graph, "rollup.price_stats@v2.hv20")
    assert (body["session"], body["count"], body["nulls"]) == (END.isoformat(), 4, 1)
    assert body["unknown"] is None and body["info"]["dtype"] == "float32"
    median = {q["q"]: q["value"] for q in body["quantiles"]}[0.5]
    assert median == pytest.approx(0.21)
    assert sum(b["count"] for b in body["histogram"]) == 3 and body["categories"] == []
    assert (
        _distribution(graph, "rollup.price_stats@v2.hv20", PREVIOUS.isoformat())["session"]
        == PREVIOUS.isoformat()
    )


def test_categorical_distribution(graph: Graph) -> None:
    body = _distribution(graph, "instrument.security_type")
    assert {c["value"]: c["count"] for c in body["categories"]} == {"COMMON_STOCK": 3, "ETF": 1}
    assert body["quantiles"] == [] and body["histogram"] == []
    label = _distribution(graph, "feature.liquidity_class")
    assert {c["value"]: c["count"] for c in label["categories"]} == {
        "HIGH": 2, "MEDIUM": 1, "LOW": 1,
    }  # fmt: skip
    earlier = _distribution(graph, "feature.liquidity_class", PREVIOUS.isoformat())
    # No option liquidity stored that day: the label is UNKNOWN for the session as a page shows
    # it (the feature values' rule), not a label computed without its input.
    assert earlier["session"] == PREVIOUS.isoformat() and earlier["categories"] == []
    assert earlier["unknown"]["code"] == "NO_PARTITION"
    pct = _distribution(graph, "feature.pct_from_high_52w")
    assert (pct["count"], pct["nulls"]) == (4, 4)  # no 52-week range stored


def test_a_feature_not_stored_for_the_session_is_unknown_not_an_older_partition(
    graph: Graph,
) -> None:
    unstored = _distribution(graph, "rollup.dividends@v2.div_ttm")
    assert unstored["unknown"]["code"] == "NO_PARTITION"
    assert (unstored["count"], unstored["categories"], unstored["histogram"]) == (0, [], [])
    before = _distribution(graph, "feature.near_52w", "2020-01-01")
    assert before["session"] == "2020-01-01" and before["unknown"]["code"] == "NO_PARTITION"


def test_a_name_outside_the_catalogue_is_unknown_feature(graph: Graph) -> None:
    body = graph(DISTRIBUTION, {"name": "rollup.nope@v1.x"})
    assert body["errors"][0]["extensions"]["code"] == "UNKNOWN_FEATURE"
