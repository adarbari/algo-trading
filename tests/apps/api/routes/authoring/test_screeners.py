"""``/screeners/{id}``: copy, draft, finalise, rebase and delete (ADR 0029), each write read
back through GraphQL (``screenDetail``, ``screenVersions``, ``myScreens``: the API's user)."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

ALICE = {"X-Act-For": "alice"}  # an admin writing for another declared user

DETAIL = """query S($id: String!) {
  screenDetail(screenerId: $id) {
    screenerId user draft draftError versions latest error working
    preset { presetId pinned current rebaseAvailable }
  }
}"""
VERSIONS = "query V($id: String!) { screenVersions(screenerId: $id) { version document } }"
MINE = "{ myScreens { screenerId status latest hasDraft presetId } }"


def _read(c: TestClient, query: str, screener_id: str | None = None) -> Any:
    variables = {"id": screener_id} if screener_id is not None else {}
    body = c.post("/graphql", json={"query": query, "variables": variables}).json()
    assert "errors" not in body, body
    return next(iter(body["data"].values()))


def _detail(c: TestClient, screener_id: str) -> Any:
    return _read(c, DETAIL, screener_id)


OWN = {
    "kind": "screener",
    "impl": "rules",
    "selection": "all_active",
    "criteria": {"price": {"field": "rollup.price_stats@v2.close", "op": "gt", "value": 10}},
}


def test_copy_finalise_and_rebase(writer_client: TestClient, root: Path) -> None:
    c = writer_client
    assert _detail(c, "vrp")["versions"] == []  # an uncopied preset
    copied = c.post("/screeners/my_vrp/copy", json={"preset": "vrp"})
    assert copied.status_code == 201
    assert copied.json()["document"] == {"id": "my_vrp", "extends": "vrp@3"}
    assert _detail(c, "my_vrp")["working"]["criteria"]["price"]["value"] == 5
    assert c.post("/screeners/my_vrp/copy", json={"preset": "vrp"}).status_code == 409
    done = c.post("/screeners/my_vrp/finalise").json()
    assert done["version"] == 1 and done["hash"]
    detail = _detail(c, "my_vrp")
    assert (detail["versions"], detail["draft"], detail["user"]) == ([1], None, "local")
    assert detail["preset"] == {
        "presetId": "vrp",
        "pinned": 3,
        "current": 3,
        "rebaseAvailable": False,
    }
    assert c.put("/screeners/my_vrp/schedule", json={}).status_code == 404  # gone
    presets = root / "site" / "presets" / "screeners" / "vrp"
    v3 = (presets / "v3.toml").read_text()
    (presets / "v4.toml").write_text(v3.replace("version = 3", "version = 4").replace("5", "7"))
    stale = _detail(c, "my_vrp")
    assert (
        stale["error"] is None and stale["working"] == detail["working"]
    )  # the pin still resolves
    assert stale["preset"]["rebaseAvailable"]
    assert c.post("/screeners/my_vrp/rebase").json()["document"]["extends"] == "vrp@4"
    assert c.post("/screeners/my_vrp/finalise").json()["version"] == 2
    versions = _read(c, VERSIONS, "my_vrp")
    assert [v["version"] for v in versions] == [1, 2]
    assert versions[0]["document"]["extends"] == "vrp@3"  # v1 is untouched
    alice = c.post("/screeners/alices/copy", json={"preset": "vrp"}, headers=ALICE)
    assert alice.status_code == 201
    assert _detail(c, "alices") is None  # alice's screens are hers only


def test_draft_put_delete_and_fail_closed_finalise(writer_client: TestClient, root: Path) -> None:
    c = writer_client
    saved = c.put("/screeners/mine/draft", json={"document": OWN | {"selection": "nope"}})
    assert saved.status_code == 200 and saved.json()["document"]["id"] == "mine"
    assert (root / "users" / "local" / "screeners" / "mine" / "draft.toml").is_file()
    broken = _detail(c, "mine")
    assert "nope" in broken["draftError"] and broken["working"] is None
    bad = c.post("/screeners/mine/finalise")
    assert bad.status_code == 400 and "nope" in bad.json()["detail"]
    assert _read(c, VERSIONS, "mine") == []
    assert c.put("/screeners/mine/draft", json={"document": OWN}).status_code == 200
    working = _detail(c, "mine")["working"]
    assert working["criteria"]["price"]["value"] == 10  # the draft, resolved
    assert c.post("/screeners/mine/finalise").json()["version"] == 1
    assert c.delete("/screeners/mine/draft").status_code == 204
    assert c.post("/screeners/mine/finalise").status_code == 404
    assert _detail(c, "nothing") is None


@pytest.mark.parametrize(
    ("url", "act_for"),
    [
        ("/screeners/mine/draft", "site"),
        ("/screeners/mine/draft", "../etc"),
        ("/screeners/mine/draft", "Alice"),
        ("/screeners/mine/draft", "mallory"),  # a valid id the registry does not declare
        ("/screeners/Mine/draft", None),
        ("/screeners/mine..x/draft", None),
    ],
)
def test_ids_and_user_labels_are_strict(
    writer_client: TestClient, root: Path, url: str, act_for: str | None
) -> None:
    headers = {} if act_for is None else {"X-Act-For": act_for}
    assert writer_client.put(url, json={"document": OWN}, headers=headers).status_code == 400
    assert not (root / "users").exists()  # nothing written anywhere


def test_delete_archives_a_screen_and_404s_a_preset(writer_client: TestClient, root: Path) -> None:
    c = writer_client
    assert c.put("/screeners/mine/draft", json={"document": OWN}).status_code == 200
    assert c.post("/screeners/mine/finalise").status_code == 200
    assert c.delete("/screeners/mine").status_code == 204
    assert _read(c, MINE) == []
    assert len(list((root / "users" / "local" / "archive" / "screeners").iterdir())) == 1
    assert c.delete("/screeners/mine").status_code == 404
    assert c.delete("/screeners/vrp").status_code == 404  # a site preset: by PR
    reused = c.put("/screeners/mine/draft", json={"document": OWN})
    assert reused.status_code == 409  # a deleted id is never reused


def test_list_has_finalised_and_draft_only_screens(writer_client: TestClient) -> None:
    c = writer_client
    assert _read(c, MINE) == []
    c.post("/screeners/vrp/copy", json={"preset": "vrp"})  # a copy: draft only
    c.put("/screeners/mine/draft", json={"document": OWN})
    c.post("/screeners/mine/finalise")
    c.put("/screeners/alices/draft", json={"document": OWN}, headers=ALICE)  # not the API's user
    listed = {s["screenerId"]: s for s in _read(c, MINE)}
    assert set(listed) == {"vrp", "mine"}
    assert (listed["vrp"]["status"], listed["vrp"]["presetId"]) == ("DRAFT", "vrp")
    assert (listed["vrp"]["hasDraft"], listed["mine"]["hasDraft"]) == (True, False)
    assert (listed["mine"]["status"], listed["mine"]["latest"]) == ("FINAL", 1)


def test_a_trader_writes_for_themselves_only(trader_client: TestClient, root: Path) -> None:
    c = trader_client
    refused = c.put("/screeners/mine/draft", json={"document": OWN}, headers=ALICE)
    assert refused.status_code == 403
    assert c.delete("/screeners/mine", headers=ALICE).status_code == 403
    assert not (root / "users").exists()  # nothing written for alice
    # ``?user=`` is retired: it is ignored, so the write is bob's own.
    own = c.put("/screeners/mine/draft", params={"user": "alice"}, json={"document": OWN})
    assert own.status_code == 200
    assert (root / "users" / "bob" / "screeners" / "mine" / "draft.toml").is_file()
    assert not (root / "users" / "alice").exists()
    named = c.put("/screeners/mine/draft", headers={"X-Act-For": "bob"}, json={"document": OWN})
    assert named.status_code == 200  # naming oneself is allowed
