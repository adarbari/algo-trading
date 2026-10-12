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
  edge(id: $id) { id status followed followedSince statusSince statusReason labels oosRevealed
                  oosHidden mine extends replaces frozenFrom screeners
                  compare { oosHidden reason rows { kind } } }
}"""
LIST = "{ edges { id mine status followed } }"


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
    assert (mine["mine"], mine["extends"], mine["status"]) == (True, "drift", "researching")
    assert (mine["followed"], mine["followedSince"]) == (False, None)
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
    refused = c.put("/edges/mine/state", json={"status": "retired"})
    assert refused.status_code == 400 and "cannot go from" in refused.json()["detail"]
    assert c.put("/edges/mine/state", json={"status": "rejected"}).status_code == 400  # a reason
    rejected = c.put("/edges/mine/state", json={"status": "rejected", "reason": "No edge."})
    assert (rejected.json()["status"], rejected.json()["reason"]) == ("rejected", "No edge.")
    mine = read(c, QUERY, id="mine")
    assert (mine["status"], mine["statusReason"]) == ("rejected", "No edge.")
    assert mine["statusSince"]
    # following is a bookmark of a site edge: it never changes the site's status
    followed = c.put("/edges/drift/state", json={"follow": True})
    assert followed.status_code == 200 and followed.json()["followed"] is True
    drift = read(c, QUERY, id="drift")
    assert (drift["followed"], drift["status"]) == (True, "candidate") and drift["followedSince"]
    assert [(e["id"], e["followed"]) for e in read(c, LIST)] == [("drift", True), ("mine", False)]
    unfollowed = c.put("/edges/drift/state", json={"follow": False})
    assert unfollowed.json()["followed"] is False
    assert read(c, QUERY, id="drift")["followed"] is False  # the bookmark is gone


def test_follow_is_for_site_edges_and_status_for_own_edges(client: TestClient) -> None:
    c = client
    assert c.post("/edges/drift/copy", json={"new_id": "mine"}).status_code == 201
    assert c.put("/edges/drift/state", json={"status": "live"}).status_code == 400
    assert c.put("/edges/mine/state", json={"follow": True}).status_code == 400
    both = c.put("/edges/mine/state", json={"follow": True, "status": "candidate"})
    assert both.status_code == 400
    unknown = c.put("/edges/mine/state", json={"status": "following"})
    assert unknown.status_code == 400 and "status" in unknown.json()["detail"]


def test_a_new_version_is_a_candidate_and_going_live_retires_the_old_one(
    client: TestClient,
) -> None:
    c = client
    made = c.post("/edges/drift/copy", json={"new_id": "drift_v2", "as_version": True})
    assert made.json()["document"]["status"] == "candidate"
    assert read(c, QUERY, id="drift_v2")["replaces"] == "drift"
    done = c.put("/edges/drift_v2/state", json={"status": "live"}).json()
    assert (done["status"], done["labels"]) == ("live", ["replaced_without_forward_test"])


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
    assert read(client, LIST) == [
        {"id": "drift", "mine": False, "status": "candidate", "followed": False}
    ]
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
    done = client.put("/edges/drift/state", json={"follow": True}, headers=ALICE)
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


def test_a_faulty_copy_file_is_served_as_a_problem_with_its_reason(
    client: TestClient, root: Path
) -> None:
    query = "{ edgeProblems { edgeId reason } }"
    assert read(client, query) == []
    (root / "users" / "local" / "edges").mkdir(parents=True)
    (root / "users" / "local" / "edges" / "broken.toml").write_text('extends = "ghost"\n')
    (problem,) = read(client, query)
    assert problem["edgeId"] == "broken" and "extends: no edge 'ghost'" in problem["reason"]
    assert [e["id"] for e in read(client, LIST)] == ["drift"]


class _Keep:
    def __init__(self) -> None:
        self.rows: list[Any] = []

    def submit(self, row: Any) -> bool:
        self.rows.append(row)
        return True


def test_a_save_records_edge_revised_after_the_write_and_never_before_a_refusal(
    client: TestClient,
) -> None:
    sink = _Keep()
    client.app.state.feedback = sink  # type: ignore[attr-defined]
    assert client.post("/edges/drift/copy", json={"new_id": "mine"}).status_code == 201
    assert (
        client.put("/edges/mine", json={"document": {"extends": "drift", "top_k": 2}}).status_code
        == 200
    )
    assert (
        client.put("/edges/mine", json={"document": {"extends": "drift", "top_k": 2}}).status_code
        == 200
    )
    assert (
        client.put(
            "/edges/mine",
            json={"document": {"extends": "drift", "top_k": 3}, "draft_session_id": "s1"},
        ).status_code
        == 200
    )
    bad = client.put("/edges/mine", json={"document": {"extends": "drift", "screeners": ["nope"]}})
    assert (
        bad.status_code == 400
        and client.put("/edges/drift", json={"document": {}}).status_code == 409
    )
    assert [r["event"] for r in sink.rows] == ["edge_revised", "edge_revised"]  # unchanged: quiet
    assert "top_k" in sink.rows[1]["payload"] and "s1" in sink.rows[1]["payload"]


def test_a_failing_sink_does_not_fail_an_edge_save(client: TestClient) -> None:
    class Down:
        def submit(self, row: Any) -> bool:
            raise RuntimeError("down")

    client.app.state.feedback = Down()  # type: ignore[attr-defined]
    assert client.post("/edges/drift/copy", json={"new_id": "mine"}).status_code == 201
    assert (
        client.put("/edges/mine", json={"document": {"extends": "drift", "top_k": 2}}).status_code
        == 200
    )
