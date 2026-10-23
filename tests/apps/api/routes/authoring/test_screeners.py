"""``/screeners/{id}``: copy, draft, finalise, rebase and delete (ADR 0029), each write read
back through GraphQL (``screenDetail``, ``screenVersions``, ``myScreens``: the API's user)."""

import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from algotrade.config.site.features.definitions import feature_definitions
from algotrade.config.user import UserContext
from algotrade.core.model.completion import Completion
from algotrade.features.expressions.fingerprint import fingerprint
from algotrade.services.ondemand.screens import RunRequest
from algotrade.storage.configs.writer import FileConfigWriter
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app
from tests.helpers.api_store import as_user

ALICE = {"X-Act-For": "alice"}  # an admin writing for another declared user

DETAIL = """query S($id: String!) {
  screenDetail(screenerId: $id) {
    screenerId user draft draftError versions latest error working
    preset { presetId pinned current rebaseAvailable }
  }
}"""
VERSIONS = "query V($id: String!) { screenVersions(screenerId: $id) { version document } }"
MINE = "{ myScreens { screenerId status latest hasDraft presetId } }"


def _read(c: TestClient, query: str, screener_id: str | None = None) -> Any:
    variables = {"id": screener_id} if screener_id is not None else {}
    body = c.post("/graphql", json={"query": query, "variables": variables}).json()
    assert "errors" not in body, body
    return next(iter(body["data"].values()))


def _detail(c: TestClient, screener_id: str) -> Any:
    return _read(c, DETAIL, screener_id)


OWN = {
    "kind": "screener",
    "impl": "rules",
    "selection": "all_active",
    "criteria": {"price": {"field": "rollup.price_stats@v2.close", "op": "gt", "value": 10}},
}


def test_copy_finalise_and_rebase(writer_client: TestClient, root: Path) -> None:
    c = writer_client
    assert _detail(c, "vrp")["versions"] == []  # an uncopied preset
    copied = c.post("/screeners/my_vrp/copy", json={"preset": "vrp"})
    assert copied.status_code == 201
    assert copied.json()["document"] == {"id": "my_vrp", "extends": "vrp@3"}
    assert _detail(c, "my_vrp")["working"]["criteria"]["price"]["value"] == 5
    assert c.post("/screeners/my_vrp/copy", json={"preset": "vrp"}).status_code == 409
    done = c.post("/screeners/my_vrp/finalise").json()
    assert done["version"] == 1 and done["hash"]
    detail = _detail(c, "my_vrp")
    assert (detail["versions"], detail["draft"], detail["user"]) == ([1], None, "local")
    assert detail["preset"] == {
        "presetId": "vrp",
        "pinned": 3,
        "current": 3,
        "rebaseAvailable": False,
    }
    assert c.put("/screeners/my_vrp/schedule", json={}).status_code == 404  # gone
    presets = root / "site" / "presets" / "screeners" / "vrp"
    v3 = (presets / "v3.toml").read_text()
    (presets / "v4.toml").write_text(v3.replace("version = 3", "version = 4").replace("5", "7"))
    stale = _detail(c, "my_vrp")
    assert (
        stale["error"] is None and stale["working"] == detail["working"]
    )  # the pin still resolves
    assert stale["preset"]["rebaseAvailable"]
    assert c.post("/screeners/my_vrp/rebase").json()["document"]["extends"] == "vrp@4"
    assert c.post("/screeners/my_vrp/finalise").json()["version"] == 2
    versions = _read(c, VERSIONS, "my_vrp")
    assert [v["version"] for v in versions] == [1, 2]
    assert versions[0]["document"]["extends"] == "vrp@3"  # v1 is untouched
    alice = c.post("/screeners/alices/copy", json={"preset": "vrp"}, headers=ALICE)
    assert alice.status_code == 201
    assert _detail(c, "alices") is None  # alice's screens are hers only


def test_draft_put_delete_and_fail_closed_finalise(writer_client: TestClient, root: Path) -> None:
    c = writer_client
    saved = c.put("/screeners/mine/draft", json={"document": OWN | {"selection": "nope"}})
    assert saved.status_code == 200 and saved.json()["document"]["id"] == "mine"
    assert (root / "users" / "local" / "screeners" / "mine" / "draft.toml").is_file()
    broken = _detail(c, "mine")
    assert "nope" in broken["draftError"] and broken["working"] is None
    bad = c.post("/screeners/mine/finalise")
    assert bad.status_code == 400 and "nope" in bad.json()["detail"]
    assert _read(c, VERSIONS, "mine") == []
    assert c.put("/screeners/mine/draft", json={"document": OWN}).status_code == 200
    working = _detail(c, "mine")["working"]
    assert working["criteria"]["price"]["value"] == 10  # the draft, resolved
    assert c.post("/screeners/mine/finalise").json()["version"] == 1
    assert c.delete("/screeners/mine/draft").status_code == 204
    assert c.post("/screeners/mine/finalise").status_code == 404
    assert _detail(c, "nothing") is None


@pytest.mark.parametrize(
    ("url", "act_for"),
    [
        ("/screeners/mine/draft", "site"),
        ("/screeners/mine/draft", "../etc"),
        ("/screeners/mine/draft", "Alice"),
        ("/screeners/mine/draft", "mallory"),  # a valid id the registry does not declare
        ("/screeners/Mine/draft", None),
        ("/screeners/mine..x/draft", None),
    ],
)
def test_ids_and_user_labels_are_strict(
    writer_client: TestClient, root: Path, url: str, act_for: str | None
) -> None:
    headers = {} if act_for is None else {"X-Act-For": act_for}
    assert writer_client.put(url, json={"document": OWN}, headers=headers).status_code == 400
    assert not (root / "users").exists()  # nothing written anywhere


def test_delete_archives_a_screen_and_404s_a_preset(writer_client: TestClient, root: Path) -> None:
    c = writer_client
    assert c.put("/screeners/mine/draft", json={"document": OWN}).status_code == 200
    assert c.post("/screeners/mine/finalise").status_code == 200
    assert c.delete("/screeners/mine").status_code == 204
    assert _read(c, MINE) == []
    assert len(list((root / "users" / "local" / "archive" / "screeners").iterdir())) == 1
    assert c.delete("/screeners/mine").status_code == 404
    assert c.delete("/screeners/vrp").status_code == 404  # a site preset: by PR
    reused = c.put("/screeners/mine/draft", json={"document": OWN})
    assert reused.status_code == 409  # a deleted id is never reused


def test_list_has_finalised_and_draft_only_screens(writer_client: TestClient) -> None:
    c = writer_client
    assert _read(c, MINE) == []
    c.post("/screeners/vrp/copy", json={"preset": "vrp"})  # a copy: draft only
    c.put("/screeners/mine/draft", json={"document": OWN})
    c.post("/screeners/mine/finalise")
    c.put("/screeners/alices/draft", json={"document": OWN}, headers=ALICE)  # not the API's user
    listed = {s["screenerId"]: s for s in _read(c, MINE)}
    assert set(listed) == {"vrp", "mine"}
    assert (listed["vrp"]["status"], listed["vrp"]["presetId"]) == ("DRAFT", "vrp")
    assert (listed["vrp"]["hasDraft"], listed["mine"]["hasDraft"]) == (True, False)
    assert (listed["mine"]["status"], listed["mine"]["latest"]) == ("FINAL", 1)


def test_a_trader_writes_for_themselves_only(trader_client: TestClient, root: Path) -> None:
    c = trader_client
    refused = c.put("/screeners/mine/draft", json={"document": OWN}, headers=ALICE)
    assert refused.status_code == 403
    assert c.delete("/screeners/mine", headers=ALICE).status_code == 403
    assert not (root / "users").exists()  # nothing written for alice
    # ``?user=`` is retired: it is ignored, so the write is bob's own.
    own = c.put("/screeners/mine/draft", params={"user": "alice"}, json={"document": OWN})
    assert own.status_code == 200
    assert (root / "users" / "bob" / "screeners" / "mine" / "draft.toml").is_file()
    assert not (root / "users" / "alice").exists()
    named = c.put("/screeners/mine/draft", headers={"X-Act-For": "bob"}, json={"document": OWN})
    assert named.status_code == 200  # naming oneself is allowed


class Keep:
    """A feedback sink that keeps the rows (ADR 0066)."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def submit(self, row: Any) -> bool:
        self.rows.append(dict(row))
        return True

    @property
    def names(self) -> list[str]:
        return [r["event"] for r in self.rows]


class Answer:
    """A text model that answers one canned draft."""

    names = ("canned",)

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
    ) -> Any:
        criteria = [{"id": "price", "field": "rollup.price_stats@v2.close", "op": "gt", "value": 5}]
        return Completion(json.dumps({"criteria": criteria}), "m", "canned", call_id="call-1")


def _describe_it(c: TestClient) -> tuple[Keep, str]:
    """``c`` with a canned model and a keeping sink, one sentence drafted: (sink, session id)."""
    sink = Keep()
    c.app.state.feedback, c.app.state.text_model = sink, Answer()  # type: ignore[attr-defined]
    drafted = c.post("/screeners/mine/draft-from-text", json={"text": "price over $5"})
    assert drafted.status_code == 200, drafted.text
    session = drafted.json()["draft_session_id"]
    drafts = c.app.state.drafts  # type: ignore[attr-defined]
    kept = drafts.get(session, "local", "mine")  # the canned answer offers no choices: say it did
    drafts.put(
        session,
        replace(
            kept,
            terms=frozenset({"liquid"}),
            formulas={"draft_near_high": FINGERPRINT, "draft_other": "ffffffffffff"},
        ),
    )
    return sink, session


def test_describe_it_events_follow_the_draft_to_the_saved_screen(writer_client: TestClient) -> None:
    c = writer_client
    sink, session = _describe_it(c)
    assert sink.names == ["draft_requested", "draft_returned"] and session
    assert {r["draft_session_id"] for r in sink.rows} == {session}
    assert sink.rows[1]["call_ids"] == "call-1" and sink.rows[1]["draft_hash"]
    price = {"field": "rollup.price_stats@v2.close", "op": "gt", "value": 12}
    edited = OWN | {"criteria": {"price": price}}
    saved = c.put("/screeners/mine/draft", json={"document": edited, "draft_session_id": session})
    assert saved.status_code == 200
    assert sink.names[-1] == "draft_saved"
    assert (
        '"changed":[{' in sink.rows[-1]["payload"]
    )  # 5 became 12: the diff, derived on the server
    done = c.post("/screeners/mine/finalise", json={"draft_session_id": session}).json()
    last = sink.rows[-1]
    assert last["event"] == "screen_finalised" and last["saved_hash"] == done["hash"]
    assert last["sentence"] == "price over $5" and last["user"] == "local"


def test_a_hand_built_screen_and_a_failed_write_record_nothing(writer_client: TestClient) -> None:
    c = writer_client
    sink, session = _describe_it(c)
    before = len(sink.rows)
    assert c.put("/screeners/hand/draft", json={"document": OWN}).status_code == 200  # no id
    assert c.post("/screeners/hand/finalise").json()["version"] == 1  # no body: still fine
    assert len(sink.rows) == before
    bad = OWN | {"selection": "nope"}  # fails closed at finalise: the write did not happen
    c.put("/screeners/mine/draft", json={"document": bad, "draft_session_id": session})
    after_save = len(sink.rows)
    assert c.post("/screeners/mine/finalise", json={"draft_session_id": session}).status_code == 400
    assert len(sink.rows) == after_save  # no screen_finalised for a refused finalise
    c.delete("/screeners/mine")  # the screen goes: a later save of its id is a conflict, 409
    refused = c.put("/screeners/mine/draft", json={"document": OWN, "draft_session_id": session})
    assert refused.status_code == 409 and len(sink.rows) == after_save


CHOICES = [
    {"event": "choice_made", "subject": "liquid", "picked": 1},
    {"event": "formula_accepted", "subject": "draft_near_high"},
    {"event": "formula_skipped", "subject": "draft_other"},
]


def test_choices_become_one_event_each_after_the_write_and_a_resend_is_the_same_row(
    writer_client: TestClient,
) -> None:
    c = writer_client
    sink, session = _describe_it(c)
    body = {"document": OWN, "draft_session_id": session, "choices": CHOICES}
    assert c.put("/screeners/mine/draft", json=body).status_code == 200
    made = [r for r in sink.rows if r["event"] in {x["event"] for x in CHOICES}]
    assert [r["event"] for r in made] == [x["event"] for x in CHOICES]
    assert json.loads(made[0]["payload"]) == {"subject": "liquid", "picked": 1}
    assert json.loads(made[1]["payload"]) == {"subject": "draft_near_high", "picked": None}
    assert {r["draft_session_id"] for r in made} == {session} and made[0]["sentence"]
    c.put("/screeners/mine/draft", json=body)  # the web re-sends them with the next save
    c.post("/screeners/mine/finalise", json={"draft_session_id": session, "choices": CHOICES})
    ids = [r["event_id"] for r in sink.rows if r["event"] in {x["event"] for x in CHOICES}]
    assert len(ids) == 9 and len(set(ids)) == 3  # the same three keys: the table keeps one each


def test_a_choice_whose_subject_the_answer_never_offered_records_nothing(
    writer_client: TestClient,
) -> None:
    c = writer_client
    sink, session = _describe_it(c)
    stray = [
        {"event": "choice_made", "subject": "invented", "picked": 0},
        {"event": "formula_accepted", "subject": "liquid"},  # a term is not a formula
        {"event": "formula_skipped", "subject": "draft_other"},
    ]
    c.put(
        "/screeners/mine/draft",
        json={"document": OWN, "draft_session_id": session, "choices": stray},
    )
    made = [r for r in sink.rows if r["event"] in {x["event"] for x in stray}]
    assert [r["event"] for r in made] == ["formula_skipped"]


def test_choices_of_a_session_that_is_not_theirs_or_of_a_refused_write_record_nothing(
    writer_client: TestClient,
) -> None:
    c = writer_client
    sink, session = _describe_it(c)
    before = len(sink.rows)
    c.put("/screeners/mine/draft", json={"document": OWN, "choices": CHOICES})  # no session id
    c.put(
        "/screeners/other/draft",
        json={"document": OWN, "draft_session_id": session, "choices": CHOICES},
    )  # another screen's id
    c.put(
        "/screeners/mine/draft",
        json={"document": OWN, "draft_session_id": "unknown", "choices": CHOICES},
    )
    assert not [r for r in sink.rows[before:] if r["event"] in {x["event"] for x in CHOICES}]
    c.delete("/screeners/mine")
    refused = c.put(
        "/screeners/mine/draft",
        json={"document": OWN, "draft_session_id": session, "choices": CHOICES},
    )
    assert refused.status_code == 409
    assert not [r for r in sink.rows[before:] if r["event"] in {x["event"] for x in CHOICES}]


def test_bad_choices_are_refused_and_a_failing_sink_does_not_fail_the_save(
    writer_client: TestClient,
) -> None:
    c = writer_client
    wrong = {"event": "draft_saved", "subject": "x"}
    assert (
        c.put("/screeners/mine/draft", json={"document": OWN, "choices": [wrong]}).status_code
        == 422
    )
    many = [CHOICES[0]] * 51
    assert (
        c.put("/screeners/mine/draft", json={"document": OWN, "choices": many}).status_code == 422
    )
    _sink, session = _describe_it(c)

    class Down:
        def submit(self, row: Any) -> bool:
            raise RuntimeError("down")

    c.app.state.feedback = Down()  # type: ignore[attr-defined]
    body = {"document": OWN, "draft_session_id": session, "choices": CHOICES}
    assert c.put("/screeners/mine/draft", json=body).status_code == 200


def test_a_failing_sink_does_not_fail_the_save(writer_client: TestClient) -> None:
    c = writer_client

    class Down:
        def submit(self, row: Any) -> bool:
            raise RuntimeError("down")

    c.app.state.feedback = Down()  # type: ignore[attr-defined]
    ok = c.put("/screeners/mine/draft", json={"document": OWN, "draft_session_id": "whatever"})
    assert ok.status_code == 200


def test_a_whole_iteration_reads_back_from_the_rows_and_finalising_closes_the_session(
    writer_client: TestClient,
) -> None:
    c = writer_client
    sink, session = _describe_it(c)
    price = {"field": "rollup.price_stats@v2.close", "op": "gt", "value": 12}
    hand = OWN | {"criteria": {"price": price}}  # the trader edits between descriptions
    again = c.post(
        "/screeners/mine/draft-from-text",
        json={"text": "and liquid", "document": hand, "draft_session_id": session},
    ).json()["draft_session_id"]
    assert again == session
    final = OWN | {"criteria": {"price": price | {"value": 15}}}
    c.put("/screeners/mine/draft", json={"document": final, "draft_session_id": session})
    rows = [r for r in sink.rows if r["draft_session_id"] == session]
    asked = [(r["seq"], r["sentence"]) for r in rows if r["event"] == "draft_requested"]
    assert asked == [(1, "price over $5"), (2, "and liquid")]
    sent = json.loads(next(r for r in rows if r["seq"] == 2)["payload"])["current_criteria"]
    assert sent["criteria"]["price"]["value"] == 12
    saved = json.loads(rows[-1]["payload"])["saved_criteria"]["criteria"]
    assert rows[-1]["event"] == "draft_saved" and saved["price"]["value"] == 15
    third = c.post(
        "/screeners/mine/draft-from-text",
        json={"text": "and large cap", "draft_session_id": session},
    ).json()["draft_session_id"]
    assert third == session  # describe, save, describe: still one session
    c.post("/screeners/mine/finalise", json={"draft_session_id": session})
    assert sink.rows[-1]["event"] == "screen_finalised"
    assert sink.rows[-1]["draft_session_id"] == session and sink.rows[-1]["seq"] == 3
    later = c.post(
        "/screeners/mine/draft-from-text",
        json={"text": "another", "draft_session_id": session},
    ).json()["draft_session_id"]
    assert later != session  # finalised: a later description is a new session


FEATURE = {
    "name": "near_high_pct",
    "expr": "price_stats.hv20 * 100",
    "dtype": "float",
    "unit": "pct_points",
    "description": "hv20 in percent",
    "null_meaning": "hv20 is null",
}


FINGERPRINT = fingerprint(
    feature_definitions(
        {"t": {FEATURE["name"]: {k: v for k, v in FEATURE.items() if k != "name"}}}, "local"
    )[0]
).hash  # what the canned answer "proposed" for draft_near_high


def test_an_accepted_formula_carries_the_saved_features_formula_and_fingerprint(
    writer_client: TestClient,
) -> None:
    c = writer_client
    sink, session = _describe_it(c)
    assert c.post("/features/user", json=FEATURE).status_code == 201  # renamed from the proposal
    accepted = {
        "event": "formula_accepted",
        "subject": "draft_near_high",
        "feature": FEATURE["name"],
    }
    body = {"document": OWN, "draft_session_id": session, "choices": [accepted]}
    assert c.put("/screeners/mine/draft", json=body).status_code == 200
    (row,) = [r for r in sink.rows if r["event"] == "formula_accepted"]
    payload = json.loads(row["payload"])
    assert payload["subject"] == "draft_near_high" and payload["feature"] == "near_high_pct"
    assert payload["expression"] == "price_stats.hv20 * 100" and payload["unit"] == "pct_points"
    assert len(payload["fingerprint"]) == 12 and payload["canonical"] and payload["description"]
    c.post("/screeners/mine/finalise", json={"draft_session_id": session, "choices": [accepted]})
    ids = [r["event_id"] for r in sink.rows if r["event"] == "formula_accepted"]
    assert len(ids) == 2 and len(set(ids)) == 1  # a resend is the same row


def test_an_accepted_formula_whose_feature_is_missing_records_the_subject_only(
    writer_client: TestClient,
) -> None:
    c = writer_client
    sink, session = _describe_it(c)
    missing = {"event": "formula_accepted", "subject": "draft_near_high", "feature": "never_saved"}
    body = {"document": OWN, "draft_session_id": session, "choices": [missing]}
    assert c.put("/screeners/mine/draft", json=body).status_code == 200  # never fails the save
    (row,) = [r for r in sink.rows if r["event"] == "formula_accepted"]
    assert json.loads(row["payload"]) == {"subject": "draft_near_high", "picked": None}
    skipped = {"event": "formula_skipped", "subject": "draft_other", "feature": FEATURE["name"]}
    c.put("/screeners/mine/draft", json=body | {"choices": [skipped]})
    (row,) = [r for r in sink.rows if r["event"] == "formula_skipped"]
    assert json.loads(row["payload"]) == {"subject": "draft_other", "picked": None}


def test_a_feature_that_is_not_the_proposed_formula_records_the_subject_only(
    writer_client: TestClient,
) -> None:
    c = writer_client
    sink, session = _describe_it(c)
    other = FEATURE | {"name": "other_pct", "expr": "price_stats.hv20 * 7"}
    assert c.post("/features/user", json=other).status_code == 201
    wrong = {"event": "formula_accepted", "subject": "draft_near_high", "feature": "other_pct"}
    body = {"document": OWN, "draft_session_id": session, "choices": [wrong]}
    assert c.put("/screeners/mine/draft", json=body).status_code == 200
    (row,) = [r for r in sink.rows if r["event"] == "formula_accepted"]
    assert json.loads(row["payload"]) == {"subject": "draft_near_high", "picked": None}


def test_a_choice_resent_at_finalise_keeps_the_formula_the_save_recorded(
    writer_client: TestClient,
) -> None:
    c = writer_client
    sink, session = _describe_it(c)
    assert c.post("/features/user", json=FEATURE).status_code == 201
    accepted = {
        "event": "formula_accepted",
        "subject": "draft_near_high",
        "feature": "near_high_pct",
    }
    c.put(
        "/screeners/mine/draft",
        json={"document": OWN, "draft_session_id": session, "choices": [accepted]},
    )
    bare = {"event": "formula_accepted", "subject": "draft_near_high"}  # the client lost the name
    c.post("/screeners/mine/finalise", json={"draft_session_id": session, "choices": [bare]})
    rows = [r for r in sink.rows if r["event"] == "formula_accepted"]
    assert len(rows) == 1  # a subject-only resend (keep="last" on event_id) would replace the row
    assert json.loads(rows[0]["payload"])["fingerprint"] == FINGERPRINT


class _Runner:
    """Stands in for ``OnDemandScreens``: records the requests, or fails them."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.asked: list[tuple[str, str]] = []

    def request(self, config_id: str, user: Any, on: Any, serving: Any) -> Any:
        if self.fail:
            raise RuntimeError("no data")
        self.asked.append((config_id, user.user_id))
        return RunRequest("queued", config_id, date(2026, 10, 21), "job-1", None, None)

    def close(self) -> None:
        pass


def _client_with(runner: _Runner, api_golden: Any, root: Path) -> TestClient:
    writer = FileConfigWriter(root)
    store = replace(api_golden[0], configs=writer, user=UserContext("local"))
    app = create_app(
        ApiSettings("memory://", str(root)),
        store,
        writer,
        authenticator=as_user(),
        ondemand=runner,  # type: ignore[arg-type]
    )
    return TestClient(app)


@pytest.mark.parametrize("fail", [False, True])
def test_finalise_starts_a_one_off_run(api_golden: Any, root: Path, fail: bool) -> None:
    """Finalising a screen runs it once now (ADR 0033); a run that cannot start never fails the
    finalise."""
    runner = _Runner(fail)
    c = _client_with(runner, api_golden, root)
    assert c.post("/screeners/my_vrp/copy", json={"preset": "vrp"}).status_code == 201
    done = c.post("/screeners/my_vrp/finalise")
    assert done.status_code == 200 and done.json()["version"] == 1
    if fail:
        assert done.json()["run_job_id"] is None and done.json()["run_state"] is None
    else:
        assert (done.json()["run_job_id"], done.json()["run_state"]) == ("job-1", "queued")
        assert runner.asked == [("my_vrp", "local")]
