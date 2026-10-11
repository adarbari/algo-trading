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
from algotrade.services.read.instruments.catalogue import feature_infos

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
        self._unknown: OrderedDict[tuple[str, str, str], None] = OrderedDict()
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

    def unknown_seen(self, session_id: str, user: str, content_hash: str) -> bool:
        """Note a save of a draft this process does not remember; ``True`` when this very save
        was noted before (an autosave of an unchanged document records nothing more)."""
        key = (session_id, user, content_hash)
        with self._lock:
            seen = key in self._unknown
            self._unknown[key] = None
            self._unknown.move_to_end(key)
            while len(self._unknown) > self._size:
                self._unknown.popitem(last=False)
            return seen

    def saved(self, session_id: str, user: str, doc_id: str, content_hash: str) -> bool:
        """Note a save of ``content_hash`` for a session that is ``user``'s and ``doc_id``'s;
        ``False`` when it is the one already noted (an autosave of an unchanged draft). A
        session that is not remembered or not theirs is left untouched: ``True``."""
        with self._lock:
            item = self._items.get(session_id)
            if item is None or item.user != user or item.doc_id != doc_id:
                return True
            if item.last_saved == content_hash:
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
    features: Any,
    prompt_version: str,
) -> None:
    """``draft_returned`` and the draft remembered for the save that follows."""
    try:
        version = events.catalogue_version(list(feature_infos(features)))  # the caller's fields
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
    actor: str,
) -> None:
    """The save events share one shape: the diff against the remembered draft, its hashes."""
    if not session_id:
        return  # a hand-built screen: nothing to learn from
    try:
        content = events.document_hash(document)
        draft = memory.get(session_id, user, screener_id)
        if (
            event == events.DRAFT_SAVED
            and draft is not None
            and not memory.saved(session_id, user, screener_id, content)
        ):
            return  # an autosave of the draft already recorded
        if (
            draft is None
            and event == events.DRAFT_SAVED
            and memory.unknown_seen(session_id, user, content)
        ):
            return  # an autosave of a draft this process does not remember, already recorded
        payload: dict[str, Any] = {"content_hash": content, "actor": actor}  # who edited
        if draft is None:
            payload["draft_unknown"] = True  # not remembered here, or not this user's: no diff
            session_id = ""  # never under a session id that is not theirs
        else:
            payload["diff"] = criteria_diff(draft.document, document)
        events.emit(
            sink, event, session_id, user, KIND, screener_id,
            call_ids=draft.call_ids if draft else (),
            catalogue_version=draft.catalogue_version if draft else None,
            prompt_version=draft.prompt_version if draft else None,
            draft_hash=draft.draft_hash if draft else None,
            saved_hash=saved_hash or content,
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
    actor: str,
) -> None:
    """``draft_saved``: call after the draft was stored; ``document`` is what was stored;
    ``actor`` is who made the request (rows are filed under ``user``, whose screen it is)."""
    _saved(sink, memory, events.DRAFT_SAVED, session_id, user, screener_id, document, None, actor)


def record_finalised(
    sink: FeedbackSink,
    memory: DraftMemory,
    session_id: str | None,
    user: str,
    screener_id: str,
    document: Mapping[str, Any] | None,
    finalised_hash: str,
    actor: str,
) -> None:
    """``screen_finalised``: call after the version was written; ``document`` the draft that
    became it (``None``: unreadable, nothing is recorded), ``finalised_hash`` ``Finalised.hash``;
    ``actor`` the caller (an admin may act for a user)."""
    if document is None:
        return
    _saved(
        sink, memory, events.SCREEN_FINALISED, session_id, user, screener_id, document,
        finalised_hash, actor,
    )  # fmt: skip
