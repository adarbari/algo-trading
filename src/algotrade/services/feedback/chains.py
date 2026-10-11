"""Reassemble the chain of one screen's iteration from stored event rows (ADR 0066): the
session a row belongs to once a ``claimed_session_id`` is honoured. After an API restart the
memory of drafts is gone, so a request or save made with an earlier session id is filed under a
new session (or under none, for a save); the id the client claimed is in the payload. A claim is
honoured only when the claimed session's own rows are the same user's for the same screen, so
nothing is ever linked to a session that is not the user's."""

import json
from collections.abc import Iterable, Mapping
from typing import Any


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
