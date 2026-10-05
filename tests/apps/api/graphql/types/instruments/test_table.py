"""``Query.table`` over ``POST /graphql`` on the golden API store: the universe x catalogue
columns for one session, filtered and sorted server-side, paged, each cell a value or the
UNKNOWN code saying why; with ``keys``, the instruments asked for (Explore compare); the
caller's own features, and errors naming what was wrong."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.apps.api.graphql.conftest import Graph

HV20 = "rollup.price_stats@v2.hv20"
TABLE = """query($columns: [FeatureName!]!, $keys: [String!], $sort: String, $page: Int,
  $size: Int, $q: String, $leveraged: Boolean, $optionable: Boolean, $liquidityClass: String) {
  table(columns: $columns, keys: $keys, sort: $sort, page: $page, size: $size, q: $q,
        leveraged: $leveraged, optionable: $optionable, liquidityClass: $liquidityClass) {
    session { date missing } universeSnapshot preSnapshot sort total page size
    columns { name format }
    instruments { instrumentId symbol }
    rows unknown
  }
}"""


def table(graph: Graph, **variables: Any) -> dict[str, Any]:
    body = graph(TABLE, {"columns": [], **variables})
    assert "errors" not in body, body["errors"]
    found: dict[str, Any] = body["data"]["table"]
    return found


def symbols(found: dict[str, Any]) -> list[str]:
    return [i["symbol"] for i in found["instruments"]]


def test_the_universe_with_requested_columns(graph: Graph) -> None:
    found = table(graph, columns=[HV20, "instrument.sector", HV20], sort=f"-{HV20}")
    assert (found["session"]["date"], found["universeSnapshot"]) == ("2022-11-23", "2022-11-23")
    assert [(c["name"], c["format"]) for c in found["columns"]] == [
        (HV20, "PERCENT"), ("instrument.sector", "TEXT"),
    ]  # fmt: skip
    assert symbols(found) == ["BULL", "BBB", "AAA", "CCC"]  # missing hv20 last
    assert found["rows"][0][0] == pytest.approx(0.22)
    assert found["rows"][2][1] == "Technology"
    assert found["unknown"][3][0] in ("NULL", "NO_ROW") and found["rows"][3][0] is None
    assert (found["total"], found["sort"]) == (4, f"-{HV20}")


def test_expression_features_sort_and_filter_server_side(graph: Graph) -> None:
    liquidity = "feature.liquidity_class"
    found = table(graph, columns=[liquidity], sort=liquidity)
    assert list(zip(symbols(found), (r[0] for r in found["rows"]), strict=True)) == [
        ("AAA", "HIGH"), ("BULL", "HIGH"), ("CCC", "LOW"), ("BBB", "MEDIUM"),
    ]  # fmt: skip
    assert symbols(table(graph, liquidityClass="high")) == ["AAA", "BULL"]
    assert symbols(table(graph, leveraged=True)) == ["BULL"]
    assert symbols(table(graph, leveraged=True, optionable=False)) == []
    assert symbols(table(graph, q="bb")) == ["BBB"]


def test_one_page_per_request(graph: Graph) -> None:
    found = table(graph, size=1, page=2)
    assert (symbols(found), found["total"], found["page"], found["size"]) == (["BBB"], 4, 2, 1)
    assert found["sort"] == "symbol"


def test_keys_compare_instruments_in_the_order_asked(graph: Graph) -> None:
    found = table(graph, columns=["feature.option_tier"], keys=["CCC", "AAA"])
    assert symbols(found) == ["CCC", "AAA"] and found["sort"] is None
    assert [r[0] for r in found["rows"]] == ["D", "A"]
    missing = graph(TABLE, {"columns": [], "keys": ["AAA", "NOPE"]})
    assert missing["errors"][0]["extensions"]["code"] == "NOT_FOUND"
    assert "NOPE" in missing["errors"][0]["message"]


def test_the_callers_own_features(user_client: Callable[[str], TestClient]) -> None:
    variables = {"columns": ["feature.hv20_pct"], "sort": "-feature.hv20_pct"}
    alice = user_client("alice").post("/graphql", json={"query": TABLE, "variables": variables})
    found = alice.json()["data"]["table"]
    assert symbols(found) == ["BULL", "BBB", "AAA", "CCC"]
    assert found["rows"][0][0] == pytest.approx(22.0)
    bob = user_client("bob").post("/graphql", json={"query": TABLE, "variables": variables})
    assert bob.json()["errors"][0]["extensions"]["code"] == "UNKNOWN_FEATURE"


@pytest.mark.parametrize(
    ("variables", "code"),
    [
        ({"columns": ["rollup.x@v1.y"]}, "UNKNOWN_FEATURE"),
        ({"columns": [], "sort": "-feature.nope"}, "UNKNOWN_FEATURE"),
        ({"columns": [], "size": 5000}, "BAD_REQUEST"),
        ({"columns": ["x.y"]}, "BAD_REQUEST"),
    ],
)
def test_bad_requests_name_the_problem(graph: Graph, variables: dict[str, Any], code: str) -> None:
    body = graph(TABLE, variables)
    assert body["errors"][0]["extensions"]["code"] == code
