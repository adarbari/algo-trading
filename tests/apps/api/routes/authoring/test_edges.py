"""``/edges/{id}``: copy, save, delete and state (ADR 0053 amendment 2026-10-09), each write read
back through GraphQL (``edge``, ``edges``: the API's user) and in the user's own file."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from algotrade.services.read.evaluation import versions

ALICE = {"X-Act-For": "alice"}  # an admin writing for another declared user

SITE_EDGE = """id = "drift"
name = "Drift"
thesis = "Small names drift after earnings."
mechanism = "Underreaction."
persistence = "Limits to arbitrage."
schedule = "on_event:earnings_reaction"
universe = "all_active"
top_k = "all"
screeners = ["vrp"]
status = "candidate"
frozen_from = 2026-01-02

[outcome]
kind = "excess_return"
horizon_sessions = [20]
benchmark = "SPY"
start_offset_sessions = 1

[[sources]]
title = "Bernard and Thomas, 1989"

[quality_bar]
outcome = "a"
trigger_timing = "b"
replication = "c"
expected_size = "d"
capacity_costs = "e"
failure_modes = "f"
decoys = "g"
"""
QUERY = """query E($id: String!) {
  edge(id: $id) { id state since stateReason labels oosRevealed oosHidden mine extends replaces
                  frozenFrom screeners compare { oosHidden reason rows { kind } } }
}"""
LIST = "{ edges { id mine state } }"


@pytest.fixture
def client(writer_client: TestClient, root: Path) -> TestClient:
    folder = root / "site" / "edges"
    folder.mkdir(parents=True)
    (folder / "drift.toml").write_text(SITE_EDGE)
    return writer_client


def read(c: TestClient, query: str, **variables: Any) -> Any:
    body = c.post("/graphql", json={"query": query, "variables": variables}).json()
    assert "errors" not in body, body
    return next(iter(body["data"].values()))


def test_copy_save_and_read_back(client: TestClient, root: Path) -> None:
    c = client
    copied = c.post("/edges/drift/copy", json={"new_id": "mine"})
    assert copied.status_code == 201
    assert copied.json() == {"edge_id": "mine", "document": {"extends": "drift"}}
    assert (root / "users" / "local" / "edges" / "mine.toml").read_text().strip() == (
        'extends = "drift"'
    )
    assert c.post("/edges/drift/copy", json={"new_id": "mine"}).status_code == 409
    assert c.post("/edges/ghost/copy", json={"new_id": "other"}).status_code == 404
    saved = c.put("/edges/mine", json={"document": {"extends": "drift", "top_k": 2}})
    assert saved.status_code == 200 and saved.json()["document"]["top_k"] == 2
    mine = read(c, QUERY, id="mine")
    assert (mine["mine"], mine["extends"], mine["state"]) == (True, "drift", "researching")
    assert mine["oosHidden"] and mine["compare"]["reason"] == "You have not run this edge yet"
    assert [(e["id"], e["mine"]) for e in read(c, LIST)] == [("drift", False), ("mine", True)]
    assert read(c, QUERY, id="drift")["compare"] is None  # a site edge is not compared


def test_save_fails_closed_and_never_a_site_edges_id(client: TestClient, root: Path) -> None:
    c = client
    assert c.post("/edges/drift/copy", json={"new_id": "mine"}).status_code == 201
    path = root / "users" / "local" / "edges" / "mine.toml"
    before = path.read_text()
    bad = c.put("/edges/mine", json={"document": {"extends": "drift", "screeners": ["nope"]}})
    assert bad.status_code == 400 and "no screener preset named" in bad.json()["detail"]
    assert path.read_text() == before
    assert c.put("/edges/drift", json={"document": {"top_k": 2}}).status_code == 409
    assert not (root / "users" / "local" / "edges" / "drift.toml").exists()


def test_state_follow_reject_and_the_reveal(client: TestClient) -> None:
    c = client
    assert c.post("/edges/drift/copy", json={"new_id": "mine"}).status_code == 201
    shown = c.put("/edges/mine/state", json={"reveal_oos": True})
    assert shown.json()["oos_revealed"] and shown.json()["labels"] == ["oos_viewed_during_tuning"]
    assert not read(c, QUERY, id="mine")["oosHidden"]
    refused = c.put("/edges/mine/state", json={"state": "retired"})
    assert refused.status_code == 400 and "cannot go from" in refused.json()["detail"]
    assert c.put("/edges/mine/state", json={"state": "rejected"}).status_code == 400  # a reason
    rejected = c.put("/edges/mine/state", json={"state": "rejected", "reason": "No edge."})
    assert (rejected.json()["state"], rejected.json()["reason"]) == ("rejected", "No edge.")
    followed = c.put("/edges/drift/state", json={"state": "following"})  # a site edge, no copy
    assert followed.status_code == 200 and followed.json()["state"] == "following"
    assert read(c, QUERY, id="drift")["state"] == "following"
    assert [(e["id"], e["state"]) for e in read(c, LIST)] == [
        ("drift", "following"),
        ("mine", "rejected"),
    ]


def test_a_new_version_is_a_trial_and_replacing_retires_the_old_one(client: TestClient) -> None:
    c = client
    assert c.put("/edges/drift/state", json={"state": "following"}).status_code == 200
    made = c.post("/edges/drift/copy", json={"new_id": "drift_v2", "as_version": True})
    assert made.json()["document"]["follow"]["state"] == "trial"
    v2 = read(c, QUERY, id="drift_v2")
    assert (v2["state"], v2["replaces"]) == ("trial", "drift")
    done = c.put("/edges/drift_v2/state", json={"state": "following"}).json()
    assert done["labels"] == ["replaced_without_forward_test"]  # no forward sessions have passed
    assert read(c, QUERY, id="drift")["state"] == "retired"


def test_delete_archives_the_edge_and_the_id_is_not_reused(client: TestClient, root: Path) -> None:
    c = client
    assert c.post("/edges/drift/copy", json={"new_id": "mine"}).status_code == 201
    assert c.post("/edges/mine/copy", json={"new_id": "mine_two"}).status_code == 201
    assert c.delete("/edges/mine").status_code == 409  # another extends it
    assert c.delete("/edges/mine_two").status_code == 204
    assert c.delete("/edges/mine").status_code == 204
    assert c.delete("/edges/mine").status_code == 404
    assert len(list((root / "users" / "local" / "archive" / "edges").iterdir())) == 2
    assert c.post("/edges/drift/copy", json={"new_id": "mine"}).status_code == 409
    assert [e["id"] for e in read(c, LIST)] == ["drift"]


@pytest.mark.parametrize("act_for", ["site", "../etc", "mallory"])
def test_user_labels_are_strict(client: TestClient, root: Path, act_for: str) -> None:
    done = client.post("/edges/drift/copy", json={"new_id": "mine"}, headers={"X-Act-For": act_for})
    assert done.status_code == 400
    assert not (root / "users").exists()


def test_an_admin_writes_for_another_user_and_a_trader_only_for_themself(
    client: TestClient, trader_client: TestClient, root: Path
) -> None:
    assert (
        client.post("/edges/drift/copy", json={"new_id": "mine"}, headers=ALICE).status_code == 201
    )
    assert (root / "users" / "alice" / "edges" / "mine.toml").is_file()
    assert read(client, LIST) == [{"id": "drift", "mine": False, "state": "researching"}]
    other = trader_client.post(
        "/edges/drift/copy", json={"new_id": "x"}, headers={"X-Act-For": "alice"}
    )
    assert other.status_code == 403


def test_the_published_document_is_for_admins_only(
    client: TestClient, trader_client: TestClient
) -> None:
    assert client.post("/edges/drift/copy", json={"new_id": "mine"}).status_code == 201
    assert (
        client.put("/edges/mine", json={"document": {"extends": "drift", "top_k": 3}}).status_code
        == 200
    )
    document = "query D($id: String!) { publishedEdgeDocument(id: $id) }"
    text = read(client, document, id="mine")
    assert 'id = "mine"' in text and "top_k = 3" in text and "extends" not in text
    denied = trader_client.post("/graphql", json={"query": document, "variables": {"id": "drift"}})
    assert denied.json()["errors"][0]["extensions"]["code"] == "FORBIDDEN"


def test_following_is_judged_against_the_acted_for_users_verdict_not_the_callers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen_users: list[str] = []

    def verdict_level(ctx: Any, edge_id: str) -> str:
        seen_users.append(ctx.user.user_id)
        return "not_working"

    monkeypatch.setattr(versions, "verdict_level", verdict_level)
    done = client.put("/edges/drift/state", json={"state": "following"}, headers=ALICE)
    assert done.status_code == 200
    assert seen_users == ["alice"]  # the admin is "local"; the verdict is alice's view
    assert done.json()["labels"] == ["followed_against_verdict"]


def test_an_admin_publishes_any_users_copy(client: TestClient) -> None:
    assert (
        client.post("/edges/drift/copy", json={"new_id": "mine"}, headers=ALICE).status_code == 201
    )
    assert (
        client.put(
            "/edges/mine", json={"document": {"extends": "drift", "top_k": 4}}, headers=ALICE
        ).status_code
        == 200
    )
    document = (
        "query D($id: String!, $user: String) { publishedEdgeDocument(id: $id, user: $user) }"
    )
    assert read(client, document, id="mine") is None  # the admin's own view has no such edge
    text = read(client, document, id="mine", user="alice")
    assert 'id = "mine"' in text and "top_k = 4" in text
