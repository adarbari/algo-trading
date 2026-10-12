"""Reassemble the chain of one screen's iteration from stored event rows (ADR 0066): the
session a row belongs to once a ``claimed_session_id`` is honoured. After an API restart the
memory of drafts is gone, so a request or save made with an earlier session id is filed under a
new session (or under none, for a save); the id the client claimed is in the payload. A claim is
honoured only when the claimed session's own rows are the same user's for the same screen, so
nothing is ever linked to a session that is not the user's.

A golden candidate is a chain with a ``screen_finalised`` event: its sentences in time order
(``ts``, not ``seq``: ``seq`` restarts at 1 when a restart is relinked) with the criteria in force
at each, and the ``saved_criteria`` of the last finalise as its final criteria. A chain that was
only saved (a working draft), discarded (the rows cannot tell) or never finalised is unlabelled."""

import json
from collections.abc import Iterable, Mapping
from typing import Any

from algotrade.services.feedback import events

STARTED, FINALISED = events.DRAFT_REQUESTED, events.SCREEN_FINALISED


def _claimed(row: Mapping[str, Any]) -> str | None:
    try:
        payload = json.loads(row.get("payload") or "{}")
    except (TypeError, ValueError):
        return None
    claimed = payload.get("claimed_session_id") if isinstance(payload, dict) else None
    return claimed if isinstance(claimed, str) and claimed else None


def linked_sessions(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """``rows`` each with ``chain_id``: the session it belongs to, a claimed one when that
    session has rows of the same ``user`` and ``doc_id``, else its own (``""`` stays unlinked)."""
    rows = list(rows)
    owners = {(r["draft_session_id"], r["user"], r["doc_id"]) for r in rows}
    claim_of: dict[str, str] = {}
    for r in rows:
        claimed = _claimed(r)
        if claimed and (claimed, r["user"], r["doc_id"]) in owners:
            claim_of.setdefault(r["draft_session_id"] or f"row:{r['event_id']}", claimed)

    def root(key: str) -> str:
        seen = {key}
        while key in claim_of and claim_of[key] not in seen:
            key = claim_of[key]
            seen.add(key)
        return key

    out = []
    for r in rows:
        own = r["draft_session_id"]
        key = own or f"row:{r['event_id']}"
        linked = root(key)
        out.append({**r, "chain_id": own if linked == key else linked})
    return out


def _payload(row: Mapping[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(row.get("payload") or "{}")
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def golden_candidates(
    rows: Iterable[Mapping[str, Any]], truncated: bool = False
) -> list[dict[str, Any]]:
    """The labelled cases of ``rows``: one per linked chain that ends in ``screen_finalised``,
    ``{"chain_id", "user", "doc_id", "sentences": [{"ts", "sentence", "current_criteria"}],
    "final_criteria", "source_event", "source_events"}`` (``source_event``: the final event's id;
    ``source_events``: the ids of every event of the chain, in time order).
    ``truncated``: ``rows`` were cut at a row cap (the oldest were lost), so a chain whose first
    event is at or before the oldest event loaded may be missing earlier ones and is dropped.
    A chain that starts before the window ``rows`` were
    read for (``since``) comes back partial: its early sentences are missing. Pass only rows from
    the viewer-filtered ``load_drafting_events``, never rows read around it."""
    rows = list(rows)
    oldest = min((r["ts"] for r in rows), default=None)
    chains: dict[str, list[dict[str, Any]]] = {}
    for r in linked_sessions(rows):
        if r["chain_id"]:
            chains.setdefault(r["chain_id"], []).append(r)
    cases = []
    for chain_id, members in chains.items():
        members.sort(key=lambda r: (r["ts"], r.get("seq") or 0, r["event_id"]))  # stable on ties
        if truncated and members[0]["ts"] <= oldest:
            continue  # its start may be among the events the cap cut
        done = [r for r in members if r["event"] == FINALISED]
        if not done:
            continue  # saved, discarded or abandoned: a working draft, unlabelled
        final = done[-1]
        asked = [r for r in members if r["event"] == STARTED and r["ts"] <= final["ts"]]
        cases.append({
            "chain_id": chain_id,
            "user": final["user"],
            "doc_id": final["doc_id"],
            "sentences": [
                {"ts": r["ts"], "sentence": r["sentence"],
                 "current_criteria": _payload(r).get("current_criteria")}
                for r in asked
            ],
            "final_criteria": _payload(final).get("saved_criteria"),
            "source_event": final["event_id"],
            "source_events": [r["event_id"] for r in members],
        })  # fmt: skip
    return cases
