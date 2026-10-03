from fastapi.testclient import TestClient


def test_nightly_lists_sessions_with_steps(client: TestClient) -> None:
    runs = client.get("/admin/runs/nightly", params={"limit": 5}).json()
    assert len(runs) == 1
    run = runs[0]
    assert (run["session"], run["status"], run["duration_s"]) == ("2022-11-23", "partial", 300.0)
    steps = {s["name"]: s for s in run["steps"]}
    assert steps["bars"]["counts"] == {"rows": 11}
    assert steps["chains"]["status"] == "PARTIAL"
    assert run["problems"] == ["steps not complete: chains"]


def test_nightly_limit_is_validated(client: TestClient) -> None:
    assert client.get("/admin/runs/nightly", params={"limit": 0}).status_code == 422


def test_run_detail_groups_failures_by_reason(client: TestClient, ids: dict[str, str]) -> None:
    body = client.get(f"/admin/runs/{ids['chains']}").json()
    assert body["items_total"] == 3
    assert body["items_by_status"] == {"OK": 1, "NO_CHAIN": 1, "STALE_DATA": 1}
    groups = {g["reason"]: g for g in body["failures"]}
    assert set(groups) == {"NO_CHAIN", "STALE_DATA: chain is for <date>"}
    stale = groups["STALE_DATA: chain is for <date>"]
    assert stale["examples"] == ["CCC"]
    assert stale["statuses"] == ["STALE_DATA: chain is for 2022-11-21"]


def test_unknown_or_invalid_run_is_404(client: TestClient) -> None:
    assert client.get("/admin/runs/nope").status_code == 404
    assert client.get("/admin/runs/.hidden").status_code == 404


def test_run_items_lists_every_item_with_its_code(client: TestClient, ids: dict[str, str]) -> None:
    items = client.get(f"/admin/runs/{ids['chains']}/items").json()
    assert items == [
        {"key": "AAA", "code": "OK", "status": "OK"},
        {"key": "BBB", "code": "NO_CHAIN", "status": "NO_CHAIN"},
        {"key": "CCC", "code": "STALE_DATA", "status": "STALE_DATA: chain is for 2022-11-21"},
    ]
    assert client.get("/admin/runs/nope/items").status_code == 404
