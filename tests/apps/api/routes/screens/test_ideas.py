from pathlib import Path

from fastapi.testclient import TestClient

from algotrade.config.user import UserContext
from algotrade.services.explore.store import store_over
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app


def test_ideas_one_row_per_ticker_ranked_with_every_pick(client: TestClient) -> None:
    body = client.get("/ideas").json()
    assert (body["session"], body["total"], body["priority"]) == ("2022-11-23", 2, [])
    first, second = body["items"]
    # No priority stored: screens rank by id (premium < vrp_scanner), then score: AAA (100) first.
    assert (first["rank"], first["symbol"]) == (1, "AAA")
    assert [(p["config_id"], p["decision"]) for p in first["picks"]] == [
        ("premium", "QUALIFIED"),
        ("vrp_scanner", "QUALIFIED"),
    ]
    assert first["picks"][1]["columns"] == {"spread": 0.05}
    assert first["picks"][1]["criterion_values"] == {"iv30": 0.62}
    assert (first["picks"][0]["flags"], first["picks"][1]["flags"]) == ([], ["leveraged_inverse"])
    assert body["screeners"] == [  # a site preset shows its own name, else its id
        {"config_id": c, "user": "site", "name": name, "version": 1}
        for c, name in (("premium", "premium"), ("vrp_scanner", "VRP"))
    ]
    assert (first["next_earnings_date"], first["days_to_earnings"]) == ("2022-12-01", 6)
    assert first["closest_expiry_dte"] == 30  # the nearest stored expiry (2022-12-23)
    assert first["earnings_before_expiry"] is True  # earnings 2022-12-01
    assert second["symbol"] == "BBB"
    near = second["picks"][0]
    assert near["reasons"] == "iv rank 40 < 50"
    assert near["criteria"] == [
        {
            "criterion_id": "iv_rank",
            "field": "iv_rank",
            "outcome": "NEAR",
            "value": 40.0,
            "distance": 10.0,
        }
    ]
    assert (second["next_earnings_date"], second["days_to_earnings"]) == (None, None)


def test_ideas_limit_and_date(client: TestClient) -> None:
    assert [i["symbol"] for i in client.get("/ideas", params={"limit": 1}).json()["items"]] == [
        "AAA"
    ]
    before = client.get("/ideas", params={"date": "2021-01-04"})  # nothing stored by then
    assert before.status_code == 200
    assert (before.json()["session"], before.json()["items"], before.json()["total"]) == (
        None, [], 0
    )  # fmt: skip
    assert client.get("/ideas", params={"user": "Bad User"}).status_code == 400
    assert client.get("/ideas", params={"limit": 0}).status_code == 422


def test_ideas_on_an_empty_store_is_an_empty_list_not_a_404(tmp_path: Path) -> None:
    """The real app before any screener has run: 200 with no session, never a 404."""
    store = store_over(MemoryBackend(), FileConfigStore(tmp_path), UserContext("local"))
    empty = TestClient(create_app(ApiSettings("memory://", "config"), store))
    response = empty.get("/ideas")
    assert response.status_code == 200
    body = response.json()
    assert (body["session"], body["items"], body["screeners"], body["total"]) == (None, [], [], 0)
