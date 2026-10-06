"""``POST /screeners/{id}/draft-from-text`` over the golden store: a canned model's answer
becomes the draft the Builder loads (with what was dropped), nothing is saved, an empty
sentence is a 400, an over-long one a 422, and an app without a model answers 503."""

import json
from typing import Any

from fastapi.testclient import TestClient

from algotrade.core.model.errors import ModelUnavailableError
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.main import create_app
from tests.helpers.api_store import as_user

PRICE = "rollup.price_stats@v2.close"
ANSWER = {
    "criteria": [
        {"id": "active", "field": "instrument.status", "op": "eq", "value": "ACTIVE"},
        {"id": "price", "field": PRICE, "op": "gt", "value": 5, "why": "over $5"},
        {
            "id": "iv_rank",
            "field": "rollup.nope@v1.iv_rank",
            "op": "gte",
            "value": 0.5,
            "why": "IV rank above 50%",
        },
    ],
    "tie_break": {"field": PRICE, "descending": True},
    "notes": ["no IV rank field in the catalogue"],
}


class Canned:
    def __init__(self, answer: Any) -> None:
        self.answer, self.asked = json.dumps(answer), 0

    def complete(self, system: str, user: str) -> str:
        self.asked += 1
        return self.answer


class Down:
    def complete(self, system: str, user: str) -> str:
        raise ModelUnavailableError("llama at http://localhost:11434/v1: HTTP 429 slow down")


def app_with(store: ReadStore, model: Any) -> TestClient:
    return TestClient(
        create_app(
            ApiSettings("memory://", "config"), store, drafter=model, authenticator=as_user()
        )
    )


def test_a_sentence_becomes_a_draft_with_what_was_dropped(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    model = Canned(ANSWER)
    client = app_with(api_golden[0], model)
    response = client.post(
        "/screeners/my_screen/draft-from-text",
        json={"text": "active stocks over $5 with IV rank above 50%"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["screener_id"] == "my_screen" and model.asked == 1
    assert body["document"]["criteria"] == {
        "active": {"field": "instrument.status", "op": "eq", "value": "ACTIVE"},
        "price": {"field": PRICE, "op": "gt", "value": 5},
    }
    assert body["document"]["rank"] == {"tie_break": PRICE}
    assert body["dropped"] == [
        {
            "id": "iv_rank",
            "field": "rollup.nope@v1.iv_rank",
            "reason": "field 'rollup.nope@v1.iv_rank' is not in the catalogue (IV rank above 50%)",
        }
    ]
    assert body["notes"] == ["no IV rank field in the catalogue"]
    # Nothing was saved: the user's configs have no such screen.
    store = api_golden[0]
    assert store.configs.load(store.user.user_id, "screeners", "my_screen") is None


def test_the_current_document_goes_along(api_golden: tuple[ReadStore, dict[str, str]]) -> None:
    client = app_with(api_golden[0], Canned(ANSWER))
    current = {"id": "my_screen", "criteria": {"price": {"field": PRICE, "op": "gt", "value": 1}}}
    response = client.post(
        "/screeners/my_screen/draft-from-text", json={"text": "over $5", "document": current}
    )
    assert response.status_code == 200, response.text


def test_bad_sentences(api_golden: tuple[ReadStore, dict[str, str]]) -> None:
    client = app_with(api_golden[0], Canned(ANSWER))
    assert client.post("/screeners/s/draft-from-text", json={"text": "   "}).status_code == 400
    assert client.post("/screeners/s/draft-from-text", json={"text": "x" * 1001}).status_code == 422
    assert client.post("/screeners/s/draft-from-text", json={}).status_code == 422


def test_no_model_is_a_503_with_the_reason(client: TestClient) -> None:
    response = client.post("/screeners/s/draft-from-text", json={"text": "stocks over $5"})
    assert response.status_code == 503
    assert "config/site/llm.toml" in response.json()["detail"]


def test_a_model_that_cannot_answer_is_a_503(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    response = app_with(api_golden[0], Down()).post(
        "/screeners/s/draft-from-text", json={"text": "stocks over $5"}
    )
    assert response.status_code == 503 and "HTTP 429" in response.json()["detail"]
