"""Read-your-writes of the screener write routes (ADR 0077 decision 16): each route changes
what ``MyScreens``, ``ScreenDetail``, ``ScreenVersions`` and ``ScreenerConfigs`` (the web's
operations, all cached per user) serve on the very next read, while another user's answers
are unchanged. Every test runs with and without the process-local write epoch (``conftest``)."""

from pathlib import Path

from fastapi.testclient import TestClient

from tests.contract.api.read_your_writes.conftest import Gate

MINE = "query MyScreens { myScreens { screenerId status latest hasDraft presetId } }"
DETAIL = """query ScreenDetail($id: String!) {
  screenDetail(screenerId: $id) {
    screenerId draft draftError versions latest working
    preset { presetId pinned current rebaseAvailable }
  }
}"""
VERSIONS = "query ScreenVersions($id: String!) { screenVersions(screenerId: $id) { version } }"
CONFIGS = 'query ScreenerConfigs { configs(kind: "screener") { configId scope } }'
OWN = {
    "kind": "screener",
    "impl": "rules",
    "selection": "all_active",
    "criteria": {"price": {"field": "rollup.price_stats@v2.close", "op": "gt", "value": 10}},
}


def ids(rows: list[dict[str, object]]) -> list[object]:
    return [r["screenerId"] for r in rows]


def test_copy_shows_the_new_screen(
    gate: Gate, writer_client: TestClient, trader_client: TestClient
) -> None:
    c = writer_client
    assert gate.warm(c, MINE) == []
    assert gate.warm(c, DETAIL, id="my_vrp") is None
    assert gate.warm(trader_client, MINE) == []
    assert c.post("/screeners/my_vrp/copy", json={"preset": "vrp"}).status_code == 201
    assert ids(gate.fresh(c, MINE)) == ["my_vrp"]
    assert gate.fresh(c, DETAIL, id="my_vrp")["working"]["criteria"]["price"]["value"] == 5
    assert gate.warm(trader_client, MINE) == []  # bob has none, still served from his entry


def test_draft_put_shows_the_draft_and_a_replacement(gate: Gate, writer_client: TestClient) -> None:
    c = writer_client
    assert gate.warm(c, MINE) == []
    assert gate.warm(c, DETAIL, id="mine") is None
    assert c.put("/screeners/mine/draft", json={"document": OWN}).status_code == 200
    assert ids(gate.fresh(c, MINE)) == ["mine"]
    assert gate.fresh(c, DETAIL, id="mine")["working"]["criteria"]["price"]["value"] == 10
    gate.warm(c, DETAIL, id="mine")
    edited = OWN | {"criteria": {"price": OWN["criteria"]["price"] | {"value": 20}}}  # type: ignore[index]
    assert c.put("/screeners/mine/draft", json={"document": edited}).status_code == 200
    assert gate.fresh(c, DETAIL, id="mine")["working"]["criteria"]["price"]["value"] == 20


def test_draft_delete_removes_the_draft(gate: Gate, writer_client: TestClient) -> None:
    c = writer_client
    assert c.put("/screeners/mine/draft", json={"document": OWN}).status_code == 200
    assert c.post("/screeners/mine/finalise").status_code == 200
    assert c.put("/screeners/mine/draft", json={"document": OWN}).status_code == 200
    assert gate.warm(c, DETAIL, id="mine")["draft"] is not None
    assert c.delete("/screeners/mine/draft").status_code == 204
    assert gate.fresh(c, DETAIL, id="mine")["draft"] is None


def test_finalise_shows_the_new_version(gate: Gate, writer_client: TestClient) -> None:
    c = writer_client
    assert c.put("/screeners/mine/draft", json={"document": OWN}).status_code == 200
    assert gate.warm(c, VERSIONS, id="mine") == []
    assert gate.warm(c, MINE)[0]["latest"] is None
    assert gate.warm(c, DETAIL, id="mine")["draft"] is not None
    assert "mine" not in {r["configId"] for r in gate.warm(c, CONFIGS)}
    assert c.post("/screeners/mine/finalise").status_code == 200
    assert gate.fresh(c, VERSIONS, id="mine") == [{"version": 1}]
    assert gate.fresh(c, MINE)[0]["latest"] == 1
    assert gate.fresh(c, DETAIL, id="mine")["draft"] is None
    assert "mine" in {r["configId"] for r in gate.fresh(c, CONFIGS)}


def test_rebase_moves_the_pin_to_the_current_preset(
    gate: Gate, writer_client: TestClient, root: Path
) -> None:
    c = writer_client
    assert c.post("/screeners/my_vrp/copy", json={"preset": "vrp"}).status_code == 201
    assert c.post("/screeners/my_vrp/finalise").status_code == 200
    presets = root / "site" / "presets" / "screeners" / "vrp"  # a new preset version lands by PR
    v3 = (presets / "v3.toml").read_text()
    (presets / "v4.toml").write_text(v3.replace("version = 3", "version = 4").replace("5", "7"))
    before = gate.warm(c, DETAIL, id="my_vrp")
    assert before["preset"]["pinned"] == 3 and before["draft"] is None
    assert c.post("/screeners/my_vrp/rebase").status_code == 200
    after = gate.fresh(c, DETAIL, id="my_vrp")
    assert after["draft"] is not None and after["draft"]["extends"] == "vrp@4"


def test_delete_removes_the_screen(
    gate: Gate, writer_client: TestClient, trader_client: TestClient
) -> None:
    c = writer_client
    assert c.put("/screeners/mine/draft", json={"document": OWN}).status_code == 200
    assert c.post("/screeners/mine/finalise").status_code == 200
    assert ids(gate.warm(c, MINE)) == ["mine"]
    assert gate.warm(c, DETAIL, id="mine")["latest"] == 1
    assert "mine" in {r["configId"] for r in gate.warm(c, CONFIGS)}
    assert gate.warm(trader_client, MINE) == []
    assert c.delete("/screeners/mine").status_code == 204
    assert gate.fresh(c, MINE) == []
    assert gate.fresh(c, DETAIL, id="mine") is None
    assert "mine" not in {r["configId"] for r in gate.fresh(c, CONFIGS)}
    assert gate.warm(trader_client, MINE) == []
