"""Feedback event rows (ADR 0066): the event names, the sentence and payload clipped, content
hashes that ignore key order, and ``emit`` that never raises."""

import json
from collections.abc import Mapping
from typing import Any

import pytest

from algotrade.services.feedback import events
from algotrade.services.feedback.events import (
    EVENTS,
    MAX_PAYLOAD,
    MAX_SENTENCE,
    MAX_VALUE,
    NoFeedback,
    bounded,
    catalogue_version,
    document_hash,
    emit,
    payload_text,
    row_of,
)


class Keep:
    def __init__(self) -> None:
        self.rows: list[Mapping[str, Any]] = []

    def submit(self, row: Mapping[str, Any]) -> bool:
        self.rows.append(row)
        return True


class Raises:
    def submit(self, row: Mapping[str, Any]) -> bool:
        raise RuntimeError("queue exploded")


def test_the_event_names_are_the_designed_eight() -> None:
    assert EVENTS == (
        "draft_requested", "draft_returned", "choice_made", "formula_accepted",
        "formula_skipped", "draft_saved", "screen_finalised", "edge_revised",
    )  # fmt: skip


def test_the_sentence_is_clipped_and_call_ids_are_delimited() -> None:
    row = row_of("draft_requested", "s1", "abhi", "screen", "mine", sentence="x" * 5000,
                 call_ids=("c1", "", "c2"))  # fmt: skip
    assert len(row["sentence"]) == MAX_SENTENCE and row["sentence"].endswith("…")
    assert row["call_ids"] == "c1,c2"
    assert row["event_id"] and row["payload"] is None and row["catalogue_version"] is None


def test_an_unknown_event_or_kind_is_refused_when_built() -> None:
    with pytest.raises(ValueError, match="unknown feedback event"):
        row_of("nope", "s", "u", "screen", "d")
    with pytest.raises(ValueError, match="unknown document kind"):
        row_of("draft_saved", "s", "u", "table", "d")


def test_a_big_payload_stays_valid_json_and_says_it_was_cut() -> None:
    small = payload_text({"b": 1, "a": 2})
    assert small == '{"a":2,"b":1}'
    big = payload_text({"diff": "y" * 10 * MAX_PAYLOAD})
    assert big is not None and len(big) < MAX_PAYLOAD
    cut = json.loads(big)
    assert cut["truncated"] is True and cut["chars"] > MAX_PAYLOAD
    assert payload_text({}) is None and payload_text(None) is None


def test_hashes_follow_content_not_key_order() -> None:
    a = {"id": "s", "criteria": {"p": {"field": "f", "op": "gt", "value": 1}}}
    b = {"criteria": {"p": {"value": 1, "op": "gt", "field": "f"}}, "id": "s"}
    assert document_hash(a) == document_hash(b)
    assert document_hash(a) != document_hash({**a, "id": "t"})
    assert catalogue_version(["b", "a"]) == catalogue_version(["a", "b"])
    assert catalogue_version(["a"]) != catalogue_version(["a", "b"])


def test_emit_submits_and_never_raises() -> None:
    sink = Keep()
    assert emit(sink, events.DRAFT_SAVED, "s1", "abhi", "screen", "mine", saved_hash="h")
    assert sink.rows[0]["saved_hash"] == "h" and sink.rows[0]["event"] == "draft_saved"
    assert emit(Raises(), events.DRAFT_SAVED, "s1", "abhi", "screen", "mine") is False
    assert emit(sink, "bogus", "s1", "abhi", "screen", "mine") is False  # a bad row is dropped
    assert emit(NoFeedback(), events.DRAFT_SAVED, "s", "u", "screen", "d") is False
    assert len(sink.rows) == 1


def test_a_snapshot_is_kept_whole_up_to_eight_thousand_characters_then_flagged() -> None:
    small = {"criteria": {"a": 1}}
    assert bounded(small) == small
    cut = bounded({"criteria": "z" * (MAX_VALUE + 1)})
    assert cut["truncated"] is True and cut["chars"] > MAX_VALUE and len(cut["head"]) <= MAX_VALUE
    assert row_of("draft_requested", "s", "u", "screen", "d", seq=2)["seq"] == 2
