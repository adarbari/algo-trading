"""``POST /screeners/preview`` over the golden store: an unsaved draft evaluated on the latest
stored session, the top rows, and a 400 naming the path of an invalid draft."""

from typing import Any

from fastapi.testclient import TestClient

DRAFT: dict[str, Any] = {
    "id": "my_draft",
    "kind": "screener",
    "impl": "rules",
    "selection": "liquid_optionable",
    "criteria": {
        "price": {"field": "rollup.price_stats@v2.close", "op": "gt", "value": 5},
        "vol": {
            "field": "rollup.price_stats@v2.hv20",
            "op": "lte",
            "value": 0.6,
            "mode": "soft",
            "tolerance": 0.2,
        },
    },
    "columns": {"close": "rollup.price_stats@v2.close"},
}


def test_preview_evaluates_an_unsaved_draft(client: TestClient) -> None:
    response = client.post("/screeners/preview", json={"spec": DRAFT, "limit": 2})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["screener_id"] == "my_draft" and body["session"] == "2022-11-23"
    assert body["total"] >= len(body["rows"]) and len(body["rows"]) <= 2
    assert [s["criterion_id"] for s in body["funnel"]] == ["price", "vol"]
    assert sum(body["decisions"].values()) == body["total"] == body["coverage"]["selected"]
    first = body["rows"][0]
    assert first["rank"] == 1 and set(first["columns"]) == {"close"}
    assert [c["criterion_id"] for c in first["criteria"]] == ["price", "vol"]
    again = client.post("/screeners/preview", json={"spec": DRAFT, "limit": 2}).json()
    assert again["cached"] and again["rows"] == body["rows"]


def test_an_invalid_draft_is_a_400_with_its_path(client: TestClient) -> None:
    bad = {**DRAFT, "criteria": {**DRAFT["criteria"], "vol": {**DRAFT["criteria"]["vol"],
                                                               "tolerance": -1}}}  # fmt: skip
    response = client.post("/screeners/preview", json={"spec": bad})
    assert response.status_code == 400
    assert "criteria.vol.tolerance" in response.json()["detail"]


def test_a_body_out_of_range_is_a_422(client: TestClient) -> None:
    assert client.post("/screeners/preview", json={"spec": DRAFT, "limit": 5000}).status_code == 422
