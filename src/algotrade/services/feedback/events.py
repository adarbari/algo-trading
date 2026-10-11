"""One feedback event of a drafting session as a row of ``feedback/drafting_events`` (ADR 0066):
the event names, the clipping of the sentence and the payload, the content hash of a document,
and ``emit``, which builds a row and hands it to a ``FeedbackSink`` without ever raising: an
event that cannot be built or queued is dropped (logged) and the request goes on."""

import hashlib
import json
import logging
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from algotrade.core.model.completion import clip

DRAFT_REQUESTED = "draft_requested"
DRAFT_RETURNED = "draft_returned"
CHOICE_MADE = "choice_made"
FORMULA_ACCEPTED = "formula_accepted"
FORMULA_SKIPPED = "formula_skipped"
DRAFT_SAVED = "draft_saved"
SCREEN_FINALISED = "screen_finalised"
EDGE_REVISED = "edge_revised"
EVENTS = (
    DRAFT_REQUESTED, DRAFT_RETURNED, CHOICE_MADE, FORMULA_ACCEPTED, FORMULA_SKIPPED,
    DRAFT_SAVED, SCREEN_FINALISED, EDGE_REVISED,
)  # fmt: skip
DOC_KINDS = ("screen", "edge")
MAX_SENTENCE = 1000  # characters of the trader's sentence kept
MAX_VALUE = 8000  # characters of one criteria snapshot's JSON kept (``bounded``)
MAX_PART = 4000  # characters of a diff, the dropped list or the notes kept (before the payload)
MAX_PAYLOAD = 32000  # characters of the whole payload's JSON kept: room for three snapshots
CALL_IDS_SEP = ","

log = logging.getLogger(__name__)


class FeedbackSink(Protocol):
    """Where events go: ``submit`` queues a row for writing and never raises (``False``: the
    row was dropped)."""

    def submit(self, row: Mapping[str, Any]) -> bool: ...


class NoFeedback:
    """The sink of an app that records nothing (tests, the OpenAPI export)."""

    def submit(self, row: Mapping[str, Any]) -> bool:
        return False


def document_hash(document: Mapping[str, Any]) -> str:
    """A short content hash of ``document`` (canonical JSON: key order does not matter), the
    same for the same screen wherever it is computed."""
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def new_session_id() -> str:
    """A fresh ``draft_session_id``: one per screen being drafted, kept by the caller across its
    successive descriptions until the screen is saved."""
    return uuid.uuid4().hex


def _cut(text: str, limit: int) -> dict[str, Any]:
    """The small valid object that stands for JSON ``text`` over ``limit``: ``truncated``, its
    length and its head."""
    return {"truncated": True, "chars": len(text), "head": clip(text, limit // 2)}


def bounded(value: Any, limit: int = MAX_VALUE) -> Any:
    """``value`` (JSON-ready) as it is when its JSON fits ``limit`` characters, else
    ``{"truncated": true, "chars": n, "head": ...}``: a snapshot never fails a request."""
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return value if len(text) <= limit else _cut(text, limit)


def payload_text(payload: Mapping[str, Any] | None) -> str | None:
    """``payload`` as compact JSON; one over ``MAX_PAYLOAD`` characters is replaced by a small
    valid object that says it was cut (``truncated``, its head)."""
    if not payload:
        return None
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    if len(text) <= MAX_PAYLOAD:
        return text
    return json.dumps(_cut(text, MAX_PAYLOAD))


def row_of(
    event: str,
    draft_session_id: str,
    user: str,
    doc_kind: str,
    doc_id: str,
    *,
    at: datetime | None = None,
    call_ids: Sequence[str] = (),
    catalogue_version: str | None = None,
    prompt_version: str | None = None,
    draft_hash: str | None = None,
    saved_hash: str | None = None,
    sentence: str | None = None,
    seq: int | None = None,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The row of one event (the point-in-time columns are stamped by the recorder). The
    sentence is clipped to ``MAX_SENTENCE``; ``ValueError`` for an event or document kind this
    module does not name."""
    if event not in EVENTS:
        raise ValueError(f"unknown feedback event {event!r}")
    if doc_kind not in DOC_KINDS:
        raise ValueError(f"unknown document kind {doc_kind!r}")
    return {
        "event_id": uuid.uuid4().hex,
        "draft_session_id": draft_session_id,
        "ts": at or datetime.now(UTC),
        "user": user,
        "doc_kind": doc_kind,
        "doc_id": doc_id,
        "event": event,
        "call_ids": CALL_IDS_SEP.join(c for c in call_ids if c) or None,
        "catalogue_version": catalogue_version,
        "prompt_version": prompt_version,
        "draft_hash": draft_hash,
        "saved_hash": saved_hash,
        "sentence": clip(sentence, MAX_SENTENCE) if sentence is not None else None,
        "seq": seq,
        "payload": payload_text(payload),
    }


def emit(
    sink: FeedbackSink,
    event: str,
    draft_session_id: str,
    user: str,
    doc_kind: str,
    doc_id: str,
    **fields: Any,
) -> bool:
    """Build the row of ``event`` and submit it; ``False`` when it was dropped. Never raises:
    a request never fails on its feedback (ADR 0066)."""
    try:
        return sink.submit(row_of(event, draft_session_id, user, doc_kind, doc_id, **fields))
    except Exception:
        log.exception("feedback event %s dropped", event)
        return False


def catalogue_version(names: Sequence[str]) -> str:
    """A short id of a field catalogue (a hash of its sorted names): two drafts made over the
    same fields share it, so a golden case says which catalogue its answer was for."""
    return hashlib.sha256("\n".join(sorted(names)).encode()).hexdigest()[:12]
