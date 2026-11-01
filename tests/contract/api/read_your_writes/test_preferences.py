"""Read-your-writes of the preference routes (ADR 0077 decision 16): a
table's saved view shows on the very next ``TableView`` read (cached per user),
and another user's view is untouched."""

from fastapi.testclient import TestClient

from tests.contract.api.read_your_writes.conftest import Gate

VIEW = """query TableView($scope: String!, $name: String) {
  view(scope: $scope, name: $name) { scope saved columns sort decisions names }
}"""
SCOPE = "screener:vrp"
CLOSE = "rollup.price_stats@v2.close"
BODY = {"columns": [CLOSE], "sort": f"-{CLOSE}", "decisions": ["QUALIFIED"]}


def test_view_put_shows_the_saved_view(
    gate: Gate, writer_client: TestClient, trader_client: TestClient
) -> None:
    c = writer_client
    assert gate.warm(c, VIEW, scope=SCOPE, name=None)["saved"] is False
    assert gate.warm(trader_client, VIEW, scope=SCOPE, name=None)["saved"] is False
    assert c.put(f"/preferences/views/{SCOPE}/view", json=BODY).status_code == 200
    saved = gate.fresh(c, VIEW, scope=SCOPE, name=None)
    assert (saved["saved"], saved["columns"], saved["sort"]) == (True, [CLOSE], f"-{CLOSE}")
    gate.warm(c, VIEW, scope=SCOPE, name=None)
    again = {"columns": [], "sort": None, "decisions": []}
    assert c.put(f"/preferences/views/{SCOPE}/view", json=again).status_code == 200
    assert gate.fresh(c, VIEW, scope=SCOPE, name=None)["columns"] == []
    assert gate.warm(trader_client, VIEW, scope=SCOPE, name=None)["saved"] is False  # bob's own


def test_view_delete_forgets_a_named_view(gate: Gate, writer_client: TestClient) -> None:
    c = writer_client
    url = f"/preferences/views/{SCOPE}/view"
    assert c.put(url, json=BODY, params={"name": "Mine"}).status_code == 200
    assert gate.warm(c, VIEW, scope=SCOPE, name="Mine")["saved"] is True
    assert gate.warm(c, VIEW, scope=SCOPE, name=None)["names"] == ["Mine"]
    assert c.delete(url, params={"name": "Mine"}).status_code == 200
    assert gate.fresh(c, VIEW, scope=SCOPE, name="Mine")["saved"] is False
    assert gate.fresh(c, VIEW, scope=SCOPE, name=None)["names"] == []


APPEARANCE = "query Appearance { appearance { theme } }"


def test_appearance_put_shows_the_saved_theme(
    gate: Gate, writer_client: TestClient, trader_client: TestClient
) -> None:
    c = writer_client
    assert gate.warm(c, APPEARANCE)["theme"] == "system"
    assert gate.warm(trader_client, APPEARANCE)["theme"] == "system"
    assert c.put("/preferences/appearance", json={"theme": "dark"}).status_code == 200
    assert gate.fresh(c, APPEARANCE)["theme"] == "dark"
    gate.warm(c, APPEARANCE)
    assert c.put("/preferences/appearance", json={"theme": "light"}).status_code == 200
    assert gate.fresh(c, APPEARANCE)["theme"] == "light"
    assert gate.warm(trader_client, APPEARANCE)["theme"] == "system"  # bob's own
