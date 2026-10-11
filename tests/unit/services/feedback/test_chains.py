"""Reassembling a screen's iteration from rows (ADR 0066): a claimed session id is honoured
only for the same user and screen, and nothing else is moved."""

import json
from typing import Any

from algotrade.services.feedback.chains import linked_sessions


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
