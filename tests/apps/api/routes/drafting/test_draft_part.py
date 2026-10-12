"""``POST /screeners/{id}/draft-part`` over the golden store (ADR 0041, amended 2026-10-12): the
browser sends back the draft it holds and the words of one part retyped; the answer is the whole
draft with that part re-drafted, nothing is saved, the same two feedback events are recorded with
``scope`` ``part`` (and the request log gets only that part's missing items), a request that fails
a check is a 400, one past the user's daily limit a 429 with a code the web shows, and the call is
tagged ``screener-draft-part``."""

import json
from typing import Any

from fastapi.testclient import TestClient

from algotrade.core.model.completion import CallTag, Completion
from algotrade.services.drafting.prompt import PROMPT_VERSION
from algotrade.services.drafting.redraft.cap import PartRedraftCap
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.feedback import DraftMemory
from algotrade_api.main import create_app
from tests.apps.api.routes.drafting.test_screeners import (
    PARTS_ANSWER,
    PRICE,
    Keep,
    _item,
)
from tests.helpers.api_store import as_user

SENTENCE = " active  over $5 \n IV rank above 50% 🚀"
PATH = "/screeners/my_screen/draft-part"
PART_ANSWER = {
    "criteria": [{"id": "price", "field": PRICE, "op": "gt", "value": 9, "part": "p1"}],
    "tie_break": None,
    "notes": [],
    "parts": [{"id": "p1", "words": "over $9", "reading": "Price above $9"}],
}


class Sequence:
    """A model that answers in turn, and keeps who it was asked as."""

    names = ("seq",)

    def names_for(self, user: str | None) -> tuple[str, ...]:
        return self.names

    def __init__(self, *answers: Any) -> None:
        self.answers = [json.dumps(a) for a in answers]
        self.tags: list[Any] = []
        self.asked: list[str] = []

    def complete(self, system: str, user: str, *, tag: Any = None, **_: Any) -> Completion:
        self.tags.append(tag)
        self.asked.append(user)
        return Completion(self.answers.pop(0), "seq", "seq", call_id=f"call-{len(self.tags)}")


def client_for(
    store: ReadStore,
    model: Any,
    sink: Any = None,
    requests: Any = None,
    cap: Any = None,
    user: str = "u1",
) -> TestClient:
    return TestClient(
        create_app(
            ApiSettings("memory://", "config"), store, text_model=model,
            authenticator=as_user(user), feedback=sink, requests=requests, part_cap=cap,
        )
    )  # fmt: skip


def first_draft(client: TestClient) -> dict[str, Any]:
    response = client.post("/screeners/my_screen/draft-from-text", json={"text": SENTENCE})
    assert response.status_code == 200, response.text
    return response.json()


def retype(draft: dict[str, Any], part: str = "p2", words: str = "over $9", **over: Any) -> Any:
    return {**draft, "part_id": part, "new_words": words, **over}


def test_a_part_is_retyped_and_the_whole_draft_comes_back(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    store = api_golden[0]
    model = Sequence(PARTS_ANSWER, PART_ANSWER)
    client = client_for(store, model)
    draft = first_draft(client)
    response = client.post(PATH, json=retype(draft))
    assert response.status_code == 200, response.text
    body = response.json()
    after = body["draft"]
    assert body["replaced_part_id"] == "p2"
    assert after["sentence"] == "active over $9 IV rank above 50% 🚀"
    assert after["document"]["criteria"]["price"]["value"] == 9
    assert after["document"]["criteria"]["active"] == draft["document"]["criteria"]["active"]
    parts = {p["id"]: p for p in after["parts"]}
    assert (parts["p2"]["words"], parts["p2"]["reading"]) == ("over $9", "Price above $9")
    assert parts["p3"]["dropped"] == ["iv_rank"] and parts["p3"]["kind"] == "not_available"
    for p in after["parts"]:  # offsets in UTF-16 units, as before
        units = after["sentence"].encode("utf-16-le")
        assert units[2 * p["start"] : 2 * p["end"]].decode("utf-16-le") == p["words"]
    assert after["draft_session_id"] == draft["draft_session_id"]
    assert [d["id"] for d in after["dropped"]] == ["iv_rank"]
    assert '"part"' not in json.dumps(after["document"])
    assert store.configs.load(store.user.user_id, "screeners", "my_screen") is None  # no write


def test_the_re_draft_call_is_tagged_as_a_part_re_draft_with_the_shared_prompt_version(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    model = Sequence(PARTS_ANSWER, PART_ANSWER)
    client = client_for(api_golden[0], model)
    assert client.post(PATH, json=retype(first_draft(client))).status_code == 200
    assert model.tags == [
        CallTag("screener-draft", "u1", PROMPT_VERSION),
        CallTag("screener-draft-part", "u1", PROMPT_VERSION),
    ]
    assert "Part words: over $9" in model.asked[1] and "active |" in model.asked[1]


def test_the_two_feedback_events_note_the_part_and_the_words_in_the_same_session(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    sink = Keep()
    client = client_for(api_golden[0], Sequence(PARTS_ANSWER, PART_ANSWER), sink)
    draft = first_draft(client)
    client.post(PATH, json=retype(draft))
    session = draft["draft_session_id"]
    rows = [r for r in sink.rows if r["draft_session_id"] == session]
    assert [(r["event"], r["seq"]) for r in rows] == [
        ("draft_requested", 1), ("draft_returned", 1),
        ("draft_requested", 2), ("draft_returned", 2),
    ]  # fmt: skip
    asked, returned = (json.loads(r["payload"]) for r in rows[2:])
    note = {"scope": "part", "part_id": "p2", "old_words": "over $5", "new_words": "over $9"}
    assert note.items() <= asked.items() and note.items() <= returned.items()
    assert "scope" not in json.loads(rows[0]["payload"] or "{}")  # the first draft is the whole one
    assert asked["current_criteria"]["criteria"]["price"]["value"] == 5  # the trader's rows
    assert rows[3]["sentence"] == "active over $9 IV rank above 50% 🚀"
    assert rows[3]["call_ids"] == "call-2" and rows[3]["prompt_version"] == PROMPT_VERSION
    assert returned["draft_criteria"]["criteria"]["price"]["value"] == 9
    assert [p["id"] for p in returned["parts"]][:3] == ["p1", "p2", "p3"]


def test_a_save_after_a_re_draft_is_diffed_against_the_re_drafted_draft(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    store = api_golden[0]
    app = create_app(
        ApiSettings("memory://", "config"), store,
        text_model=Sequence(PARTS_ANSWER, PART_ANSWER), authenticator=as_user("u1"),
    )  # fmt: skip
    client = TestClient(app)
    draft = first_draft(client)
    after = client.post(PATH, json=retype(draft)).json()["draft"]
    drafts: DraftMemory = app.state.drafts
    remembered = drafts.get(draft["draft_session_id"], "u1", "my_screen")
    assert remembered is not None and remembered.document == after["document"]
    assert remembered.seq == 2


def test_only_the_re_drafted_parts_missing_items_reach_the_request_log(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    old = _item("held_two_years_score", "over $5", "ROLLUP_FROM_STORED") | {"part": "p2"}
    first = {**PARTS_ANSWER, "missing": [old]}
    new = _item("short_squeeze_score", "a squeeze", "NEEDS_SOURCE") | {"part": "p1"}
    second = {**PART_ANSWER, "missing": [new]}
    requests = Keep()
    client = client_for(api_golden[0], Sequence(first, second), requests=requests)
    draft = first_draft(client)
    assert [r["ref"] for r in requests.rows] == ["held_two_years_score"]
    body = client.post(PATH, json=retype(draft)).json()
    assert [r["ref"] for r in requests.rows] == ["held_two_years_score", "short_squeeze_score"]
    assert [m["new_key_slug"] for m in body["draft"]["missing"]] == ["short_squeeze_score"]
    assert requests.rows[1]["draft_session_id"] == draft["draft_session_id"]


def test_a_request_that_does_not_hold_together_is_a_400_and_costs_nothing(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    sink, model = Keep(), Sequence(PARTS_ANSWER, PART_ANSWER, PART_ANSWER)
    cap = PartRedraftCap(api_golden[0].reader, lambda: 1)
    client = client_for(api_golden[0], model, sink, cap=cap)
    draft = first_draft(client)
    forged = [{**p, "words": "forged"} if p["id"] == "p2" else p for p in draft["parts"]]
    for bad in (
        retype(draft, parts=forged),
        retype(draft, part="p9"),
        retype(draft, words="  "),
        retype(draft, sentence="something else entirely"),
    ):
        assert client.post(PATH, json=bad).status_code == 400
    assert len(model.tags) == 1 and len(sink.rows) == 2  # only the first draft happened
    assert client.post(PATH, json=retype(draft)).status_code == 200  # and no place was used up


def test_the_body_is_bounded_at_the_door(api_golden: tuple[ReadStore, dict[str, str]]) -> None:
    client = client_for(api_golden[0], Sequence(PARTS_ANSWER))
    draft = first_draft(client)
    assert client.post(PATH, json=retype(draft, words="x" * 201)).status_code == 422
    assert client.post(PATH, json=retype(draft, sentence="x" * 1001)).status_code == 422
    too_many = retype(draft, notes=["n"] * 41)
    assert client.post(PATH, json=too_many).status_code == 422
    missing = {k: v for k, v in retype(draft).items() if k != "part_id"}
    assert client.post(PATH, json=missing).status_code == 422


def test_no_model_is_a_503(client: TestClient) -> None:
    body = {"sentence": "a", "document": {}, "parts": [], "part_id": "p1", "new_words": "b"}
    assert client.post(PATH, json=body).status_code == 503


def test_past_the_daily_limit_the_answer_is_a_429_with_the_code_and_nothing_is_asked(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    sink, model = Keep(), Sequence(PARTS_ANSWER, PART_ANSWER, PART_ANSWER)
    cap = PartRedraftCap(api_golden[0].reader, lambda: 1)
    client = client_for(api_golden[0], model, sink, cap=cap)
    draft = first_draft(client)
    assert client.post(PATH, json=retype(draft)).status_code == 200
    events_before = len(sink.rows)
    limited = client.post(PATH, json=retype(draft, words="over $7"))
    assert limited.status_code == 429
    body = limited.json()
    assert (body["code"], body["limit"]) == ("part_redraft_limit", 1)
    assert "daily limit of 1" in body["detail"] and body["retry_after_s"] >= 1
    assert limited.headers["Retry-After"] == str(body["retry_after_s"])
    assert len(model.tags) == 2 and len(sink.rows) == events_before  # no call, no event
    # another user has their own count
    other = client_for(api_golden[0], Sequence(PARTS_ANSWER, PART_ANSWER), cap=cap, user="u2")
    assert other.post(PATH, json=retype(first_draft(other))).status_code == 200


def test_the_default_cap_reads_the_limit_from_llm_toml(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    app = create_app(ApiSettings("memory://", "config"), api_golden[0], authenticator=as_user("u1"))
    assert app.state.part_cap._limit() == 30
