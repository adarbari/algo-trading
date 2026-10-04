"""``POST /features/check``: a formula's type and a sample from the latest stored session; an
invalid formula is a 400 with its position."""

from collections.abc import Callable

from fastapi.testclient import TestClient


def test_a_formula_is_typed_and_sampled(client: TestClient) -> None:
    body = {"expr": "price_stats.hv20 * 100", "sample": 2}
    response = client.post("/features/check", json=body)
    assert response.status_code == 200, response.text
    got = response.json()
    assert (got["type"], got["dtype"]) == ("num", "float")
    assert got["inputs"] == ["price_stats.hv20@v2"] and got["session"] == "2022-11-23"
    assert got["non_null"] >= len(got["sample"]) and len(got["sample"]) <= 2
    assert all(isinstance(s["value"], float) for s in got["sample"])


def test_a_label_formula_reports_its_categories(client: TestClient) -> None:
    got = client.post("/features/check", json={"expr": 'if(price_stats.close > 10, "hi", "lo")'})
    assert got.status_code == 200, got.text
    assert got.json()["type"] == "str" and got.json()["categories"] == ["hi", "lo"]


def test_a_bad_formula_is_a_400_with_its_position(client: TestClient) -> None:
    response = client.post("/features/check", json={"expr": "price_stats.nope + 1"})
    assert response.status_code == 400
    assert "nope" in response.json()["detail"] and "col" in response.json()["detail"]


def test_user_features_are_in_scope(user_client: Callable[[str], TestClient]) -> None:
    alice = user_client("alice").post("/features/check", json={"expr": "hv20_pct / 100"})
    assert alice.status_code == 200, alice.text
    assert alice.json()["inputs"] == ["hv20_pct@v1"]
    bob = user_client("bob").post("/features/check", json={"expr": "hv20_pct / 100"})
    assert bob.status_code == 400
