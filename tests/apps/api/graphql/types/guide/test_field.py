"""``Query.guideField`` over the repo's site configs (ADR 0051): a field's info with its guide
entry, the related fields, the site playbooks that use it (each rule as text) and the
situations that fool it, all derived by the server; a name outside the caller's catalogue is
UNKNOWN_FEATURE, a malformed one BAD_REQUEST."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from tests.apps.api.graphql.conftest import Graph

FIELD = """query F($name: FeatureName!) {
  guideField(name: $name) {
    info { name format guide { theme reads summary uses { intent op } } }
    related
    playbooks { id name family rules column rank }
    situations { name signs do affects }
  }
}"""
ADV = "rollup.price_stats@v2.adv_usd_20d"


def _field(graph: Graph, name: str) -> dict[str, Any]:
    body = graph(FIELD, {"name": name})
    assert "errors" not in body, body
    found: dict[str, Any] = body["data"]["guideField"]
    return found


def test_a_field_page_with_what_the_server_derives(graph: Graph) -> None:
    page = _field(graph, ADV)
    assert page["info"]["name"] == ADV and page["info"]["guide"]["theme"] == "liquidity"
    guide = page["info"]["guide"]
    assert guide["reads"].startswith(guide["summary"]) and guide["summary"].endswith(".")
    assert page["related"] and ADV not in page["related"]
    assert len(set(page["related"])) == len(page["related"])
    pullback = next(p for p in page["playbooks"] if p["id"] == "pullback")
    assert (pullback["name"], pullback["family"]) == ("Pullback", "trend")
    assert pullback["rules"] == ["gte 50000000 soft tolerance relative 0.2 on_miss LIQUIDITY_RISK"]
    assert page["playbooks"][0]["family"] == "trend"  # Guide order


def test_the_situations_that_fool_a_field(graph: Graph) -> None:
    page = _field(graph, "rollup.momentum@v1.rsi_14")
    names = [s["name"] for s in page["situations"]]
    assert "pending takeover" in names
    assert all("rollup.momentum@v1.rsi_14" in s["affects"] and s["do"] for s in page["situations"])


def test_bad_names(graph: Graph) -> None:
    unknown = graph(FIELD, {"name": "rollup.nope@v1.x"})
    assert unknown["errors"][0]["extensions"]["code"] == "UNKNOWN_FEATURE"
    malformed = graph(FIELD, {"name": "x.y"})
    assert malformed["errors"][0]["extensions"]["code"] == "BAD_REQUEST"


def test_a_users_own_feature_is_theirs_only(user_client: Callable[[str], TestClient]) -> None:
    def post(user: str) -> Any:
        variables = {"name": "feature.hv20_pct"}
        return user_client(user).post("/graphql", json={"query": FIELD, "variables": variables})

    assert post("bob").json()["errors"][0]["extensions"]["code"] == "UNKNOWN_FEATURE"
    page = post("alice").json()["data"]["guideField"]
    assert page["info"]["name"] == "feature.hv20_pct" and page["playbooks"] == []
    assert "rollup.price_stats@v2.hv20" in page["related"]  # its formula's input
