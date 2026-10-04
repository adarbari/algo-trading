"""``/screeners/{id}``: copy, draft, finalise, versions, rebase, schedule (ADR 0029)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

OWN = {
    "kind": "screener",
    "impl": "rules",
    "selection": "all_active",
    "criteria": {"price": {"field": "rollup.price_stats@v2.close", "op": "gt", "value": 10}},
}


def test_copy_finalise_schedule_and_rebase(writer_client: TestClient, root: Path) -> None:
    c = writer_client
    assert c.get("/screeners/vrp?user=alice").json()["versions"] == []
    copied = c.post("/screeners/my_vrp/copy?user=alice", json={"preset": "vrp"})
    assert copied.status_code == 201
    assert copied.json()["document"] == {"id": "my_vrp", "extends": "vrp@3"}
    assert c.post("/screeners/my_vrp/copy?user=alice", json={"preset": "vrp"}).status_code == 409
    done = c.post("/screeners/my_vrp/finalise?user=alice").json()
    assert done["version"] == 1 and done["hash"]
    detail = c.get("/screeners/my_vrp?user=alice").json()
    assert (detail["versions"], detail["draft"], detail["schedule"]) == ([1], None, None)
    assert detail["preset"] == {
        "preset_id": "vrp",
        "pinned": 3,
        "current": 3,
        "rebase_available": False,
    }
    scheduled = c.put("/screeners/my_vrp/schedule?user=alice", json={"schedule": "nightly"})
    assert c.get("/screeners/my_vrp?user=alice").json()["hash"] == done["hash"]
    assert scheduled.json() == {
        "screener_id": "my_vrp",
        "schedule": "nightly",
    }
    hash_v1 = c.get("/screeners/my_vrp?user=alice").json()["hash"]
    presets = root / "site" / "presets" / "screeners" / "vrp"
    v3 = (presets / "v3.toml").read_text()
    (presets / "v4.toml").write_text(v3.replace("version = 3", "version = 4").replace("5", "7"))
    stale = c.get("/screeners/my_vrp?user=alice").json()
    assert stale["error"] is None and stale["hash"] == hash_v1  # the pin still resolves
    assert stale["preset"]["rebase_available"]
    assert c.post("/screeners/my_vrp/rebase?user=alice").json()["document"]["extends"] == "vrp@4"
    assert c.post("/screeners/my_vrp/finalise?user=alice").json()["version"] == 2
    versions = c.get("/screeners/my_vrp/versions?user=alice").json()
    assert [v["version"] for v in versions] == [1, 2]
    assert versions[0]["document"]["extends"] == "vrp@3"  # v1 is untouched
    mine = {c["config_id"] for c in c.get("/configs").json() if c["scope"] == "local"}
    assert mine == set()  # alice's screens are hers only


def test_draft_put_delete_and_fail_closed_finalise(writer_client: TestClient, root: Path) -> None:
    c = writer_client
    saved = c.put("/screeners/mine/draft", json={"document": OWN | {"selection": "nope"}})
    assert saved.status_code == 200 and saved.json()["document"]["id"] == "mine"
    assert (root / "users" / "local" / "screeners" / "mine" / "draft.toml").is_file()
    assert "nope" in c.get("/screeners/mine").json()["draft_error"]
    bad = c.post("/screeners/mine/finalise")
    assert bad.status_code == 400 and "nope" in bad.json()["detail"]
    assert c.get("/screeners/mine/versions").json() == []
    assert c.put("/screeners/mine/draft", json={"document": OWN}).status_code == 200
    assert c.post("/screeners/mine/finalise").json()["version"] == 1
    assert c.delete("/screeners/mine/draft").status_code == 204
    assert c.post("/screeners/mine/finalise").status_code == 404
    assert c.get("/screeners/nothing").status_code == 404
    assert c.put("/screeners/nothing/schedule", json={"schedule": "nightly"}).status_code == 404


@pytest.mark.parametrize(
    "url",
    [
        "/screeners/mine/draft?user=site",
        "/screeners/mine/draft?user=..%2Fetc",
        "/screeners/mine/draft?user=Alice",
        "/screeners/Mine/draft",
        "/screeners/mine..x/draft",
    ],
)
def test_ids_and_user_labels_are_strict(writer_client: TestClient, root: Path, url: str) -> None:
    assert writer_client.put(url, json={"document": OWN}).status_code == 400
    assert not (root / "users").exists()  # nothing written anywhere
