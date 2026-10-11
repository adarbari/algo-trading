"""The API's Describe-it feedback (ADR 0066): events around the draft route, the save diff against
the draft the model returned, quiet autosave, no events for a hand-built screen, a draft that
belongs to someone else, a bounded memory and a sink that fails."""

from collections.abc import Mapping
from typing import Any

import pytest

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
    assert row["payload"] == '{"criteria":1,"dropped":[{"field":"f","id":"x"}]}'
    assert memory.get("s1", "abhi", "mine") is not None


def test_a_save_records_the_diff_and_an_unchanged_autosave_records_nothing_more() -> None:
    sink, memory = Keep(), DraftMemory()
    returned(sink, memory)
    edited = {"id": "mine", "criteria": {"price": {**P, "value": 10}}}
    feedback.record_draft_saved(sink, memory, "s1", "abhi", "mine", edited, "abhi")
    feedback.record_draft_saved(sink, memory, "s1", "abhi", "mine", edited, "abhi")  # an autosave
    assert sink.names == ["draft_returned", "draft_saved"]
    saved = sink.rows[1]
    assert '"changed":[{' in str(saved["payload"]) and saved["sentence"] is None
    assert saved["draft_hash"] == sink.rows[0]["draft_hash"] != saved["saved_hash"]
    feedback.record_draft_saved(sink, memory, "s1", "abhi", "mine", DOC, "abhi")  # changed again
    assert sink.names[-1] == "draft_saved" and len(sink.rows) == 3


def test_no_session_id_records_nothing() -> None:
    sink, memory = Keep(), DraftMemory()
    feedback.record_draft_saved(sink, memory, None, "abhi", "mine", DOC, "abhi")
    feedback.record_finalised(sink, memory, "", "abhi", "mine", DOC, "h", "abhi")
    assert sink.rows == []


def test_someone_elses_session_or_another_screen_is_not_diffed() -> None:
    sink, memory = Keep(), DraftMemory()
    returned(sink, memory, user="alice")
    assert memory.get("s1", "bob", "mine") is None and memory.get("s1", "alice", "other") is None
    feedback.record_finalised(sink, memory, "s1", "bob", "mine", DOC, "h", "abhi")
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
    assert feedback.record_requested(Raises(), "abhi", "mine", "x")  # still a session id
    returned(Raises(), memory)
    feedback.record_draft_saved(Raises(), memory, "s1", "abhi", "mine", DOC, "abhi")
    feedback.record_finalised(Raises(), memory, "s1", "abhi", "mine", DOC, "h", "abhi")


def test_a_save_for_a_session_this_process_does_not_remember_is_recorded_as_unknown() -> None:
    sink = Keep()
    feedback.record_draft_saved(
        sink, DraftMemory(), "gone", "abhi", "mine", DOC, "abhi"
    )  # a restart
    (row,) = sink.rows
    assert row["event"] == "draft_saved" and '"draft_unknown":true' in str(row["payload"])


def test_bobs_save_under_alices_session_id_leaves_her_session_untouched() -> None:
    sink, memory = Keep(), DraftMemory()
    returned(sink, memory, user="alice")
    feedback.record_draft_saved(sink, memory, "s1", "bob", "mine", DOC, "abhi")
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


def test_unknown_saves_are_recorded_once_per_content_and_carry_no_sentence() -> None:
    sink, memory = Keep(), DraftMemory()
    feedback.record_draft_saved(sink, memory, "gone", "abhi", "mine", DOC, "abhi")
    feedback.record_draft_saved(sink, memory, "gone", "abhi", "mine", DOC, "abhi")  # an autosave
    assert len(sink.rows) == 1 and sink.rows[0]["sentence"] is None
    other = {"id": "mine", "criteria": {}}
    feedback.record_draft_saved(sink, memory, "gone", "abhi", "mine", other, "abhi")  # changed
    assert len(sink.rows) == 2


def test_the_unknown_dedupe_is_bounded() -> None:
    sink, memory = Keep(), DraftMemory(size=2)
    for n in range(3):
        feedback.record_draft_saved(sink, memory, f"s{n}", "abhi", "mine", DOC, "abhi")
    feedback.record_draft_saved(sink, memory, "s0", "abhi", "mine", DOC, "abhi")  # evicted: again
    assert len(sink.rows) == 4


def test_a_save_and_a_finalise_carry_no_sentence_and_name_the_actor() -> None:
    sink, memory = Keep(), DraftMemory()
    returned(sink, memory, user="alice")
    edited = {"id": "mine", "criteria": {}}
    feedback.record_draft_saved(sink, memory, "s1", "alice", "mine", edited, "abhi")
    feedback.record_finalised(sink, memory, "s1", "alice", "mine", edited, "h", "abhi")
    for row in sink.rows[1:]:
        assert row["sentence"] is None and row["user"] == "alice"
        assert '"actor":"abhi"' in str(row["payload"])  # an admin acting for alice
    assert sink.rows[0]["sentence"] == "over $5"  # draft_returned holds it
