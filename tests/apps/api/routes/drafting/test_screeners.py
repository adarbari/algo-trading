"""``POST /screeners/{id}/draft-from-text`` over the golden store: a canned model's answer
becomes the draft the Builder loads (with what was dropped), nothing is saved, an empty
sentence is a 400, an over-long one a 422, and an app without a model answers 503."""

import json
from typing import Any

from fastapi.testclient import TestClient

from algotrade.core.model.completion import Completion
from algotrade.core.model.errors import ModelUnavailableError
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.main import create_app
from tests.conftest import REPO_ROOT
from tests.helpers.api_store import as_user

PRICE = "rollup.price_stats@v2.close"
CONTRACT_CASE = "liquid-optionable-near-high-support.json"
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
    names = ("canned",)

    def names_for(self, user: str | None) -> tuple[str, ...]:
        return self.names

    def __init__(self, answer: Any) -> None:
        self.answer, self.asked = json.dumps(answer), 0

    def complete(
        self,
        system: str,
        user: str,
        *,
        tag: object = None,
        schema: object = None,
        accept: object = None,
    ) -> Completion:
        self.asked += 1
        return Completion(self.answer, "canned", "canned")


class Down:
    names = ("down",)

    def names_for(self, user: str | None) -> tuple[str, ...]:
        return self.names

    def complete(
        self,
        system: str,
        user: str,
        *,
        tag: object = None,
        schema: object = None,
        accept: object = None,
    ) -> Completion:
        raise ModelUnavailableError("llama at http://localhost:11434/v1: HTTP 429 slow down")


class Keep:
    """A feedback sink that keeps the rows (ADR 0066)."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def submit(self, row: Any) -> bool:
        self.rows.append(dict(row))
        return True


def app_with(store: ReadStore, model: Any, sink: Any = None) -> TestClient:
    return TestClient(
        create_app(
            ApiSettings("memory://", "config"),
            store,
            text_model=model,
            authenticator=as_user(),
            feedback=sink,
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


def test_the_contract_fields_are_served_and_the_document_holds_only_a_criteria(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    recorded = REPO_ROOT / "tests/fixtures/drafting/golden/answers/seed-handwritten"
    client = app_with(api_golden[0], Canned(json.loads((recorded / CONTRACT_CASE).read_text())))
    response = client.post("/screeners/my_screen/draft-from-text", json={"text": "liquid"})
    assert response.status_code == 200, response.text
    body = response.json()
    (formula,) = body["formulas"]
    assert formula["name"] == "draft_near_52w_high" and formula["pending"] is True
    assert formula["criterion"]["field"] == "feature.draft_near_52w_high"
    assert formula["dry_run"]["rows"] > 0 and formula["dry_run"]["no_value_rate"] is not None
    assert body["formulas_dropped"] == []
    assert [m["key"] for m in body["missing"]] == ["support_level_history"]
    (term,) = body["unresolved"]
    assert term["term"] == "liquid" and len(term["alternatives"]) == 3
    assert "draft_near_52w_high" not in json.dumps(body["document"])
    assert "liquid" in body["document"]["criteria"]  # the default reading


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


def test_a_draft_returns_a_session_id_and_records_its_two_events(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    sink = Keep()
    client = app_with(api_golden[0], Canned(ANSWER), sink)
    body = client.post("/screeners/my_screen/draft-from-text", json={"text": "over $5"}).json()
    session = body["draft_session_id"]
    assert session and [r["event"] for r in sink.rows] == ["draft_requested", "draft_returned"]
    assert {r["draft_session_id"] for r in sink.rows} == {session}
    returned = sink.rows[1]
    assert returned["sentence"] == "over $5" and returned["doc_id"] == "my_screen"
    assert returned["draft_hash"] and returned["catalogue_version"] and returned["prompt_version"]
    payload = json.loads(returned["payload"])
    assert (
        payload["dropped"][0]["field"] == "rollup.nope@v1.iv_rank"
        and payload["dropped"][0]["reason"]
    )
    assert payload["draft_criteria"]["criteria"]["price"]["value"] == 5 and returned["seq"] == 1


def test_a_draft_that_fails_leaves_only_its_request(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    sink = Keep()
    client = app_with(api_golden[0], Down(), sink)
    assert client.post("/screeners/s/draft-from-text", json={"text": "x"}).status_code == 503
    assert [r["event"] for r in sink.rows] == ["draft_requested"]


def test_an_app_without_feedback_still_drafts(api_golden: tuple[ReadStore, dict[str, str]]) -> None:
    client = app_with(api_golden[0], Canned(ANSWER))  # no sink: the default records nothing
    body = client.post("/screeners/s/draft-from-text", json={"text": "over $5"}).json()
    assert body["draft_session_id"]


def test_a_description_with_the_previous_session_id_stays_in_the_session(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    sink = Keep()
    client = app_with(api_golden[0], Canned(ANSWER), sink)
    path = "/screeners/my_screen/draft-from-text"
    one = client.post(path, json={"text": "over $5"}).json()["draft_session_id"]
    edit = {"id": "my_screen", "criteria": {"price": {"field": PRICE, "op": "gt", "value": 9}}}
    two = client.post(path, json={"text": "liquid", "document": edit, "draft_session_id": one})
    assert two.json()["draft_session_id"] == one
    other = client.post(path, json={"text": "x", "draft_session_id": "someone-elses"})
    assert other.json()["draft_session_id"] not in (one, "someone-elses")
    asked = [
        r for r in sink.rows if r["event"] == "draft_requested" and r["draft_session_id"] == one
    ]
    assert [r["seq"] for r in asked] == [1, 2]
    assert json.loads(asked[1]["payload"])["current_criteria"]["criteria"]["price"]["value"] == 9


def _item(slug: str, span: str, feasibility: str) -> dict[str, Any]:
    return {
        "key": None, "new_key_slug": slug, "span": span, "description": f"{slug} described",
        "why_needed": "no stored field holds it", "closest": [], "feasibility": feasibility,
    }  # fmt: skip


MISSING = [
    _item("held_two_years_score", "held for two years", "ROLLUP_FROM_STORED"),
    _item("short_squeeze_score", "a squeeze", "NEEDS_SOURCE"),
]
ASKED = "over $5, held for two years and a squeeze"


def _asked(client: TestClient) -> Any:
    return client.post("/screeners/my_screen/draft-from-text", json={"text": ASKED})


def _with_requests(store: ReadStore, answer: Any, sink: Any, user: str = "u1") -> TestClient:
    return TestClient(
        create_app(
            ApiSettings("memory://", "config"), store, text_model=Canned(answer),
            authenticator=as_user(user), requests=sink,
        )
    )  # fmt: skip


def test_a_draft_with_two_missing_items_writes_two_request_rows(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    sink = Keep()
    body = _asked(_with_requests(api_golden[0], ANSWER | {"missing": MISSING}, sink)).json()
    assert [r["ref"] for r in sink.rows] == ["held_two_years_score", "short_squeeze_score"]
    assert {r["draft_session_id"] for r in sink.rows} == {body["draft_session_id"]}
    assert sink.rows[0]["span"] == "held for two years" and sink.rows[0]["key"] is None
    assert sink.rows[1]["new_slug"] == "short_squeeze_score"
    assert len(body["missing"]) == 2


def test_a_request_is_recorded_for_the_trader_whose_sentence_it_was(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    sink = Keep()
    _asked(_with_requests(api_golden[0], ANSWER | {"missing": MISSING}, sink, user="trader_7"))
    assert {r["user"] for r in sink.rows} == {"trader_7"}


def test_a_draft_with_nothing_missing_records_no_request(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    sink = Keep()
    assert _asked(_with_requests(api_golden[0], ANSWER, sink)).status_code == 200
    assert sink.rows == []


def test_a_raising_request_sink_still_returns_the_draft(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    class Raises:
        def submit(self, row: Any) -> bool:
            raise RuntimeError("full")

    response = _asked(_with_requests(api_golden[0], ANSWER | {"missing": MISSING}, Raises()))
    assert response.status_code == 200 and response.json()["draft_session_id"]


def test_the_request_recorder_is_closed_at_shutdown(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    class Closing(Keep):
        closed = False

        def close(self) -> None:
            self.closed = True

    sink = Closing()
    with _with_requests(api_golden[0], ANSWER, sink):
        assert not sink.closed
    assert sink.closed


def test_an_item_the_server_drops_is_not_recorded(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    malformed = {"new_key_slug": "dropped_one", "span": "a squeeze"}  # fields missing: not kept
    sink = Keep()
    body = _asked(_with_requests(api_golden[0], ANSWER | {"missing": [*MISSING, malformed]}, sink))
    assert [m["new_key_slug"] for m in body.json()["missing"]] == [
        "held_two_years_score", "short_squeeze_score",
    ]  # fmt: skip
    assert "dropped_one" not in [r["ref"] for r in sink.rows] and len(sink.rows) == 2
