"""The API's Describe-it feedback (ADR 0066): events around the draft route, the save diff against
the draft the model returned, quiet autosave, no events for a hand-built screen, a draft that
belongs to someone else, a bounded memory and a sink that fails."""

import json
from collections.abc import Mapping
from typing import Any

import pytest

from algotrade.services.feedback.chains import linked_sessions
from algotrade_api import feedback
from algotrade_api.feedback import DraftMemory, Remembered


class Keep:
    def __init__(self) -> None:
        self.rows: list[Mapping[str, Any]] = []

    def submit(self, row: Mapping[str, Any]) -> bool:
        self.rows.append(row)
        return True

    @property
    def names(self) -> list[str]:
        return [str(r["event"]) for r in self.rows]


class Raises:
    def submit(self, row: Mapping[str, Any]) -> bool:
        raise RuntimeError("down")


FEATURES = object()  # stands for ``ctx.features``; ``feature_infos`` is patched below


@pytest.fixture(autouse=True)
def catalogue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(feedback, "feature_infos", lambda fs: {"a": 1, "b": 2})


P = {"field": "rollup.price@v1.close", "op": "gt", "value": 5}
DOC = {"id": "mine", "criteria": {"price": P}}


def returned(sink: Any, memory: DraftMemory, session: str = "s1", user: str = "abhi") -> None:
    feedback.record_returned(
        sink, memory, session, user, "mine", "over $5", DOC, [{"id": "x", "field": "f"}],
        ("c1",), FEATURES, "1",
    )  # fmt: skip


def test_returned_records_the_draft_and_remembers_it() -> None:
    sink, memory = Keep(), DraftMemory()
    returned(sink, memory)
    (row,) = sink.rows
    assert row["event"] == "draft_returned" and row["call_ids"] == "c1"
    assert row["draft_hash"] and row["catalogue_version"] and row["prompt_version"] == "1"
    payload = json.loads(row["payload"])
    assert payload["criteria"] == 1 and payload["dropped"] == [{"id": "x", "field": "f"}]
    assert payload["draft_criteria"] == {"criteria": {"price": P}, "rank": None}
    assert payload["notes"] == [] and row["seq"] == 1
    assert memory.get("s1", "abhi", "mine") is not None


def test_a_save_records_the_diff_and_an_unchanged_autosave_records_nothing_more() -> None:
    sink, memory = Keep(), DraftMemory()
    returned(sink, memory)
    edited = {"id": "mine", "criteria": {"price": {**P, "value": 10}}}
    feedback.record_draft_saved(sink, memory, "s1", "abhi", "mine", edited)
    feedback.record_draft_saved(sink, memory, "s1", "abhi", "mine", edited)  # an autosave
    assert sink.names == ["draft_returned", "draft_saved"]
    saved = sink.rows[1]
    assert '"changed":[{' in str(saved["payload"]) and saved["sentence"] == "over $5"
    assert saved["draft_hash"] == sink.rows[0]["draft_hash"] != saved["saved_hash"]
    feedback.record_draft_saved(sink, memory, "s1", "abhi", "mine", DOC)  # changed again
    assert sink.names[-1] == "draft_saved" and len(sink.rows) == 3


def test_no_session_id_records_nothing() -> None:
    sink, memory = Keep(), DraftMemory()
    feedback.record_draft_saved(sink, memory, None, "abhi", "mine", DOC)
    feedback.record_finalised(sink, memory, "", "abhi", "mine", DOC, "h")
    assert sink.rows == []


def test_someone_elses_session_or_another_screen_is_not_diffed() -> None:
    sink, memory = Keep(), DraftMemory()
    returned(sink, memory, user="alice")
    assert memory.get("s1", "bob", "mine") is None and memory.get("s1", "alice", "other") is None
    feedback.record_finalised(sink, memory, "s1", "bob", "mine", DOC, "h")
    final = sink.rows[-1]
    assert final["event"] == "screen_finalised" and final["saved_hash"] == "h"
    assert '"draft_unknown":true' in str(final["payload"]) and final["sentence"] is None
    assert final["user"] == "bob" and final["draft_session_id"] == ""  # never alice's session


def test_the_memory_is_bounded_and_least_recently_used_goes_first() -> None:
    memory = DraftMemory(size=2)
    item = Remembered("u", "d", {}, "h", "s", (), None, None)
    memory.put("a", item)
    memory.put("b", item)
    assert memory.get("a", "u", "d") is item  # a is now the most recent
    memory.put("c", item)  # evicts b
    assert memory.get("b", "u", "d") is None
    assert memory.get("a", "u", "d") is not None and memory.get("c", "u", "d") is not None


def test_a_failing_sink_never_raises_into_the_request() -> None:
    memory = DraftMemory()
    assert feedback.record_requested(Raises(), memory, "abhi", "mine", "x", DOC)  # still an id
    returned(Raises(), memory)
    feedback.record_draft_saved(Raises(), memory, "s1", "abhi", "mine", DOC)
    feedback.record_finalised(Raises(), memory, "s1", "abhi", "mine", DOC, "h")


def test_a_save_for_a_session_this_process_does_not_remember_is_recorded_as_unknown() -> None:
    sink = Keep()
    feedback.record_draft_saved(sink, DraftMemory(), "gone", "abhi", "mine", DOC)  # a restart
    (row,) = sink.rows
    assert row["event"] == "draft_saved" and '"draft_unknown":true' in str(row["payload"])


def test_bobs_save_under_alices_session_id_leaves_her_session_untouched() -> None:
    sink, memory = Keep(), DraftMemory()
    returned(sink, memory, user="alice")
    feedback.record_draft_saved(sink, memory, "s1", "bob", "mine", DOC)
    assert memory.get("s1", "alice", "mine").last_saved is None  # type: ignore[union-attr]
    assert not any(r["user"] == "bob" and r["draft_session_id"] == "s1" for r in sink.rows)
    assert sink.rows[-1]["draft_session_id"] == ""
    assert memory.saved("s1", "bob", "mine", "h") is True  # not hers to dedupe: untouched
    assert memory.get("s1", "alice", "mine").last_saved is None  # type: ignore[union-attr]


def test_a_catalogue_that_cannot_be_read_does_not_fail_the_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(fs: Any) -> Any:
        raise RuntimeError("catalogue down")

    monkeypatch.setattr(feedback, "feature_infos", broken)
    returned(Keep(), DraftMemory())  # swallowed inside the guard


def request(sink: Any, memory: DraftMemory, text: str, doc: Any, given: str | None = None,
            user: str = "abhi") -> tuple[str, int]:  # fmt: skip
    session, seq = feedback.record_requested(sink, memory, user, "mine", text, doc, given)
    feedback.record_returned(
        sink, memory, session, user, "mine", text, doc, [], (), FEATURES, "1", seq, ["n"]
    )
    return session, seq


def test_a_description_with_the_previous_id_continues_the_session_with_the_next_seq() -> None:
    sink, memory = Keep(), DraftMemory()
    first = request(sink, memory, "over $5", DOC)
    assert first[1] == 1
    second = request(sink, memory, "and liquid", DOC, given=first[0])
    assert second == (first[0], 2)
    assert {r["draft_session_id"] for r in sink.rows} == {first[0]}
    assert [r["seq"] for r in sink.rows] == [1, 1, 2, 2]


def test_a_foreign_unknown_or_other_screen_id_starts_a_new_session() -> None:
    sink, memory = Keep(), DraftMemory()
    mine = request(sink, memory, "over $5", DOC, user="alice")[0]
    assert request(sink, memory, "x", DOC, given=mine, user="bob") != (mine, 2)  # not bob's
    assert request(sink, memory, "x", DOC, given="nope")[1] == 1
    feedback.record_requested(sink, memory, "alice", "other", "x", DOC, mine)
    assert sink.rows[-1]["draft_session_id"] != mine and sink.rows[-1]["seq"] == 1
    assert memory.get(mine, "alice", "mine").seq == 1  # type: ignore[union-attr]  # untouched


def test_a_save_keeps_the_session_open_and_finalising_ends_it() -> None:
    sink, memory = Keep(), DraftMemory()
    session, _ = request(sink, memory, "over $5", DOC)
    feedback.record_draft_saved(sink, memory, session, "abhi", "mine", DOC)
    assert request(sink, memory, "and liquid", DOC, given=session) == (session, 2)
    feedback.record_finalised(sink, memory, session, "abhi", "mine", DOC, "h")
    assert sink.rows[-1]["draft_session_id"] == session and sink.rows[-1]["seq"] == 2
    again = request(sink, memory, "next screen", DOC, given=session)
    assert again[0] != session and again[1] == 1


def test_a_failed_request_does_not_advance_seq() -> None:
    sink, memory = Keep(), DraftMemory()
    session, _ = request(sink, memory, "over $5", DOC)
    failed = feedback.record_requested(sink, memory, "abhi", "mine", "x", DOC, session)
    assert failed == (session, 2)  # the model then failed: nothing returned
    assert feedback.record_requested(sink, memory, "abhi", "mine", "x", DOC, session)[1] == 2
    feedback.record_draft_saved(sink, memory, session, "abhi", "mine", DOC)
    assert sink.rows[-1]["seq"] == 1  # the draft saved is the one returned


def test_after_a_restart_a_claimed_session_is_recorded_and_relinked_only_when_theirs() -> None:
    sink, memory = Keep(), DraftMemory()
    old = request(sink, memory, "over $5", DOC)[0]
    memory = DraftMemory()  # a restart: nothing remembered
    new, seq = request(sink, memory, "and liquid", DOC, given=old)
    assert new != old and seq == 1
    feedback.record_draft_saved(sink, memory, "gone", "abhi", "mine", DOC)  # claims an unknown id
    save = sink.rows[-1]
    assert (
        save["draft_session_id"] == ""
        and json.loads(save["payload"])["claimed_session_id"] == "gone"
    )
    feedback.record_draft_saved(sink, DraftMemory(), new, "abhi", "mine", DOC)
    chain = {r["event_id"]: r["chain_id"] for r in linked_sessions(sink.rows)}
    mine = [r for r in sink.rows if r["draft_session_id"] in (old, new)]
    assert {chain[r["event_id"]] for r in mine} == {old}  # both halves are one chain
    assert chain[sink.rows[-1]["event_id"]] == old  # the save claimed ``new``: same chain
    other = [dict(r) for r in sink.rows]  # the same rows read for a claim by someone else
    other[-1]["user"] = "mallory"
    assert linked_sessions(other)[-1]["chain_id"] == ""  # not linked: not their session


def test_a_huge_diff_notes_or_dropped_never_push_the_final_criteria_out() -> None:
    sink, memory = Keep(), DraftMemory()
    wide = {
        "id": "mine",
        "criteria": {f"c{i}": {**P, "field": "f" * 40, "value": i} for i in range(60)},
    }
    session = "s9"
    feedback.record_returned(
        sink, memory, session, "abhi", "mine", "x", {"id": "mine", "criteria": {}},
        [{"id": f"d{i}", "field": "f" * 50, "reason": "r" * 100} for i in range(200)], (),
        FEATURES, "1", 1, ["n" * 100] * 200,
    )  # fmt: skip
    feedback.record_draft_saved(sink, memory, session, "abhi", "mine", wide)
    returned_payload = json.loads(sink.rows[0]["payload"])
    assert returned_payload["dropped"]["truncated"] and returned_payload["notes"]["truncated"]
    saved = json.loads(sink.rows[-1]["payload"])
    assert saved["diff"]["truncated"] is True
    assert len(saved["saved_criteria"]["criteria"]) == 60  # the final criteria survive


def test_the_events_carry_the_criteria_in_force() -> None:
    sink, memory = Keep(), DraftMemory()
    edited = {"id": "mine", "criteria": {"price": {**P, "value": 10}}, "rank": {"x": 1}}
    session, _ = request(sink, memory, "over $5", edited)
    feedback.record_draft_saved(sink, memory, session, "abhi", "mine", DOC)
    sent = json.loads(sink.rows[0]["payload"])["current_criteria"]
    assert sent == {"criteria": {"price": {**P, "value": 10}}, "rank": {"x": 1}}
    saved = json.loads(sink.rows[-1]["payload"])
    assert saved["saved_criteria"] == {"criteria": {"price": P}, "rank": None}
    assert sink.rows[-1]["seq"] == 1


def test_a_huge_criteria_table_is_cut_with_a_flag_and_the_request_goes_on() -> None:
    sink, memory = Keep(), DraftMemory()
    big = {"id": "mine", "criteria": {f"c{i}": {**P, "note": "y" * 200} for i in range(100)}}
    request(sink, memory, "x", big)
    sent = json.loads(sink.rows[0]["payload"])["current_criteria"]
    assert sent["truncated"] is True and sent["chars"] > 8000 and len(sent["head"]) <= 4000
    returned_payload = json.loads(sink.rows[1]["payload"])
    assert (
        returned_payload["draft_criteria"]["truncated"] is True
        and returned_payload["criteria"] == 100
    )


def test_a_whole_iteration_can_be_read_back_from_the_rows() -> None:
    sink, memory = Keep(), DraftMemory()
    first = {"id": "mine", "criteria": {"price": P}}
    session, _ = request(sink, memory, "over $5", first)
    hand = {"id": "mine", "criteria": {"price": {**P, "value": 7}}}  # the trader edits
    request(sink, memory, "liquid too", hand, given=session)
    final = {"id": "mine", "criteria": {"price": {**P, "value": 8}}}
    feedback.record_draft_saved(sink, memory, session, "abhi", "mine", final)
    rows = [r for r in sink.rows if r["draft_session_id"] == session]
    asked = [(r["seq"], r["sentence"], json.loads(r["payload"])["current_criteria"]["criteria"])
             for r in rows if r["event"] == "draft_requested"]  # fmt: skip
    assert [(a[0], a[1]) for a in asked] == [(1, "over $5"), (2, "liquid too")]
    assert asked[1][2]["price"]["value"] == 7  # the edit between the descriptions
    last = json.loads(rows[-1]["payload"])["saved_criteria"]["criteria"]
    assert rows[-1]["event"] == "draft_saved" and last["price"]["value"] == 8
