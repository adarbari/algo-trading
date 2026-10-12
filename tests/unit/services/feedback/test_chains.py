"""Reassembling a screen's iteration from rows (ADR 0066): a claimed session id is honoured
only for the same user and screen, and nothing else is moved."""

import json
from typing import Any

from algotrade.services.feedback.chains import golden_candidates, linked_sessions


def row(eid: str, session: str, user: str = "u", doc: str = "d", claimed: str | None = None) -> Any:
    payload = json.dumps({"claimed_session_id": claimed}) if claimed else None
    return {"event_id": eid, "draft_session_id": session, "user": user, "doc_id": doc,
            "payload": payload}  # fmt: skip


def chains(rows: list[Any]) -> dict[str, str]:
    return {r["event_id"]: r["chain_id"] for r in linked_sessions(rows)}


def test_a_session_after_a_restart_joins_the_one_it_claimed() -> None:
    rows = [row("1", "A"), row("2", "B", claimed="A"), row("3", "", claimed="B")]
    assert chains(rows) == {"1": "A", "2": "A", "3": "A"}


def test_a_claim_of_another_user_or_screen_or_an_unknown_session_is_not_linked() -> None:
    rows = [row("1", "A"), row("2", "B", user="x", claimed="A"), row("3", "", doc="o", claimed="A"),
            row("4", "", claimed="zzz"), row("5", "C", claimed="C")]  # fmt: skip
    assert chains(rows) == {"1": "A", "2": "B", "3": "", "4": "", "5": "C"}


def test_a_claim_loop_and_a_bad_payload_do_not_hang() -> None:
    rows = [row("1", "A", claimed="B"), row("2", "B", claimed="A"), row("3", "C")]
    rows[2]["payload"] = "not json"
    assert set(chains(rows)) == {"1", "2", "3"}


FINAL = {"criteria": {"x": 2}}


def ev(eid: str, session: str, event: str, t: int, seq: int | None = None, **payload: Any) -> Any:
    return {"event_id": eid, "draft_session_id": session, "user": "u", "doc_id": "d",
            "event": event, "ts": t, "seq": seq, "sentence": f"s{eid}",
            "payload": json.dumps(payload) if payload else None}  # fmt: skip


def test_describe_save_discard_is_not_a_candidate_but_describe_save_describe_finalise_is() -> None:
    discarded = [ev("1", "A", "draft_requested", 1, 1), ev("2", "A", "draft_saved", 2, 1,
                 saved_criteria={"criteria": {"x": 1}})]  # fmt: skip
    assert golden_candidates(discarded) == []  # a saved draft is a working draft
    done = [ev("1", "B", "draft_requested", 1, 1, current_criteria={"criteria": {}}),
            ev("2", "B", "draft_saved", 2, 1, saved_criteria={"criteria": {"x": 1}}),
            ev("3", "B", "draft_requested", 3, 2, current_criteria={"criteria": {"x": 1}}),
            ev("4", "B", "screen_finalised", 4, 2, saved_criteria=FINAL)]  # fmt: skip
    (case,) = golden_candidates(discarded + done)
    assert [x["sentence"] for x in case["sentences"]] == ["s1", "s3"]
    assert case["final_criteria"] == FINAL and case["source_event"] == "4"


def test_a_relinked_chain_is_ordered_by_time_not_seq() -> None:
    rows = [ev("1", "A", "draft_requested", 1, 1), ev("2", "A", "draft_returned", 2, 1),
            ev("3", "B", "draft_requested", 3, 1, claimed_session_id="A"),  # seq restarted
            ev("4", "", "screen_finalised", 5, None, claimed_session_id="B",
               saved_criteria={"criteria": {}}),
            ev("5", "B", "draft_requested", 4, 2)]  # fmt: skip
    (case,) = golden_candidates(rows)
    assert [x["sentence"] for x in case["sentences"]] == ["s1", "s3", "s5"]
    assert case["source_event"] == "4"


def test_a_case_names_every_event_of_its_chain_and_ties_keep_a_stable_order() -> None:
    rows = [ev("2", "A", "draft_requested", 1, 1), ev("1", "A", "draft_requested", 1, 1),
            ev("3", "A", "screen_finalised", 2, None, saved_criteria=FINAL)]  # fmt: skip
    (case,) = golden_candidates(rows)
    assert case["source_events"] == ["1", "2", "3"] and case["source_event"] == "3"


def test_a_chain_at_the_edge_of_a_truncated_read_is_dropped() -> None:
    edge = [ev("1", "A", "draft_requested", 1, 1), ev("2", "A", "screen_finalised", 2,
            saved_criteria=FINAL)]  # fmt: skip
    later = [ev("3", "B", "draft_requested", 5, 1), ev("4", "B", "screen_finalised", 6,
             saved_criteria=FINAL)]  # fmt: skip
    assert [c["chain_id"] for c in golden_candidates(edge + later, truncated=True)] == ["B"]
    assert len(golden_candidates(edge + later)) == 2


def test_a_chain_that_began_before_the_window_is_dropped_and_a_seqless_one_is_flagged() -> None:
    late_start = [ev("1", "A", "draft_requested", 1, 3), ev("2", "A", "screen_finalised", 2,
                  saved_criteria=FINAL)]  # fmt: skip
    old_rows = [ev("3", "B", "draft_requested", 1, None), ev("4", "B", "screen_finalised", 2,
                saved_criteria=FINAL)]  # fmt: skip
    whole = [ev("5", "C", "draft_requested", 1, 1), ev("6", "C", "screen_finalised", 2,
             saved_criteria=FINAL)]  # fmt: skip
    got = {c["chain_id"]: c["partial"] for c in golden_candidates(late_start + old_rows + whole)}
    assert got == {"B": True, "C": False}
