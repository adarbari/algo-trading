"""The Describe-it feedback the API records (ADR 0066), server side only: ``draft_requested`` and
``draft_returned`` around the draft route, ``draft_saved`` and ``screen_finalised`` after the
screen's config write has succeeded, each carrying the ``draft_session_id`` the draft answer
returned. ``DraftMemory`` keeps, in this process and bounded, the last draft returned per
session, so a save is diffed against what the model proposed (``services.feedback.diff``); a save
with no session id, or one this process no longer remembers (a restart, an evicted entry) records
nothing for the diff, and a hand-built screen records nothing at all. Every function here
swallows its own failure: a request never fails on its feedback."""

import copy
import logging
import threading
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from algotrade.services.feedback import events
from algotrade.services.feedback.diff import criteria_diff
from algotrade.services.feedback.events import FeedbackSink, NoFeedback
from algotrade.services.feedback.recorder import open_recorder

log = logging.getLogger(__name__)
MEMORY = 512  # drafts remembered at most (the least recently used goes first)
KIND = "screen"


@dataclass(frozen=True)
class Remembered:
    """The last draft returned for a session: whose, which screen, the document, its hash and
    what produced it."""

    user: str
    doc_id: str
    document: Mapping[str, Any]
    draft_hash: str
    sentence: str
    call_ids: tuple[str, ...]
    catalogue_version: str | None
    prompt_version: str | None
    last_saved: str | None = None  # the content hash of the last save recorded: autosave is quiet


class DraftMemory:
    """A bounded, thread-safe LRU of ``Remembered`` by ``draft_session_id``."""

    def __init__(self, size: int = MEMORY) -> None:
        self._size = size
        self._items: OrderedDict[str, Remembered] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, session_id: str, item: Remembered) -> None:
        with self._lock:
            self._items[session_id] = item
            self._items.move_to_end(session_id)
            while len(self._items) > self._size:
                self._items.popitem(last=False)

    def get(self, session_id: str, user: str, doc_id: str) -> Remembered | None:
        """The draft of ``session_id`` when it is ``user``'s and for ``doc_id`` (anyone else's
        session id remembers nothing)."""
        with self._lock:
            item = self._items.get(session_id)
            if item is None or item.user != user or item.doc_id != doc_id:
                return None
            self._items.move_to_end(session_id)
            return item

    def saved(self, session_id: str, content_hash: str) -> bool:
        """Note a save of ``content_hash``; ``False`` when it is the one already noted (an
        autosave of an unchanged draft records nothing more) or the session is not remembered."""
        with self._lock:
            item = self._items.get(session_id)
            if item is None or item.last_saved == content_hash:
                return False
            self._items[session_id] = replace(item, last_saved=content_hash)
            return True


def feedback_sink(given: FeedbackSink | None, live: bool, data_url: str) -> FeedbackSink:
    """The app's sink: ``given`` (tests), else the recorder of ``feedback/drafting_events`` over
    the store at ``data_url`` when the app is the served one (``live``), else one that records
    nothing."""
    if given is not None:
        return given
    return open_recorder(data_url) if live else NoFeedback()


def record_requested(sink: FeedbackSink, user: str, screener_id: str, sentence: str) -> str:
    """``draft_requested``, before the model is asked (a draft that fails leaves its trace): the
    new ``draft_session_id``."""
    session_id = events.new_session_id()
    events.emit(
        sink, events.DRAFT_REQUESTED, session_id, user, KIND, screener_id, sentence=sentence
    )
    return session_id


def record_returned(
    sink: FeedbackSink,
    memory: DraftMemory,
    session_id: str,
    user: str,
    screener_id: str,
    sentence: str,
    document: Mapping[str, Any],
    dropped: Sequence[Mapping[str, str]],
    call_ids: Sequence[str],
    catalogue_names: Sequence[str],
    prompt_version: str,
) -> None:
    """``draft_returned`` and the draft remembered for the save that follows."""
    try:
        version = events.catalogue_version(catalogue_names)
        draft_hash = events.document_hash(document)
        memory.put(
            session_id,
            Remembered(
                user, screener_id, copy.deepcopy(dict(document)), draft_hash, sentence,
                tuple(call_ids), version, prompt_version,
            ),
        )  # fmt: skip
        raw = document.get("criteria")
        payload = {"criteria": len(raw) if isinstance(raw, Mapping) else 0,
                   "dropped": [{"id": d["id"], "field": d["field"]} for d in dropped]}  # fmt: skip
        events.emit(
            sink, events.DRAFT_RETURNED, session_id, user, KIND, screener_id,
            call_ids=call_ids, catalogue_version=version, prompt_version=prompt_version,
            draft_hash=draft_hash, sentence=sentence, payload=payload,
        )  # fmt: skip
    except Exception:
        log.exception("draft_returned not recorded")


def _saved(
    sink: FeedbackSink,
    memory: DraftMemory,
    event: str,
    session_id: str | None,
    user: str,
    screener_id: str,
    document: Mapping[str, Any],
    saved_hash: str | None,
) -> None:
    """The save events share one shape: the diff against the remembered draft, its hashes."""
    if not session_id:
        return  # a hand-built screen: nothing to learn from
    try:
        content = events.document_hash(document)
        if event == events.DRAFT_SAVED and not memory.saved(session_id, content):
            return
        draft = memory.get(session_id, user, screener_id)
        payload: dict[str, Any] = {"content_hash": content}
        if draft is None:
            payload["draft_unknown"] = True  # not remembered here: no diff to give
        else:
            payload["diff"] = criteria_diff(draft.document, document)
        events.emit(
            sink, event, session_id, user, KIND, screener_id,
            call_ids=draft.call_ids if draft else (),
            catalogue_version=draft.catalogue_version if draft else None,
            prompt_version=draft.prompt_version if draft else None,
            draft_hash=draft.draft_hash if draft else None,
            saved_hash=saved_hash or content,
            sentence=draft.sentence if draft else None,
            payload=payload,
        )  # fmt: skip
    except Exception:
        log.exception("%s not recorded", event)


def record_draft_saved(
    sink: FeedbackSink,
    memory: DraftMemory,
    session_id: str | None,
    user: str,
    screener_id: str,
    document: Mapping[str, Any],
) -> None:
    """``draft_saved``: call after the draft was stored; ``document`` is what was stored."""
    _saved(sink, memory, events.DRAFT_SAVED, session_id, user, screener_id, document, None)


def record_finalised(
    sink: FeedbackSink,
    memory: DraftMemory,
    session_id: str | None,
    user: str,
    screener_id: str,
    document: Mapping[str, Any] | None,
    finalised_hash: str,
) -> None:
    """``screen_finalised``: call after the version was written; ``document`` the draft that
    became it (``None``: unreadable, nothing is recorded), ``finalised_hash`` ``Finalised.hash``."""
    if document is None:
        return
    _saved(
        sink, memory, events.SCREEN_FINALISED, session_id, user, screener_id, document,
        finalised_hash,
    )  # fmt: skip
