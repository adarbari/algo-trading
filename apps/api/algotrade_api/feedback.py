"""The Describe-it feedback the API records (ADR 0066), server side only: ``draft_requested`` and
``draft_returned`` around the draft route, ``draft_saved`` and ``screen_finalised`` after the
screen's config write has succeeded, ``edge_revised`` after an edge document's. The screen events
each carry the ``draft_session_id`` the draft answer returned. A session is one screen's whole
iteration: a draft request may carry the id of the session it continues (the same user, the same
screen, not yet saved: else a new session), each request has its ``seq`` in the session, and the
events carry what was in force (the criteria sent with a request, the draft returned, the criteria
saved), so a golden case can be read from the rows. ``DraftMemory`` keeps, in this process and
bounded, the last draft returned per session, so a save is diffed against what the model proposed
(``services.feedback.diff``); a save with no session id, or one this process no longer remembers
(a restart, an evicted entry) records nothing for the diff, and a hand-built screen records
nothing at all. Every function here swallows its own failure: a request never fails on its
feedback."""

import copy
import hashlib
import logging
import threading
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from algotrade.services.feedback import events
from algotrade.services.feedback.diff import criteria_diff, criteria_snapshot, document_diff
from algotrade.services.feedback.events import FeedbackSink, NoFeedback
from algotrade.services.feedback.recorder import open_recorder
from algotrade.services.feedback.request_recorder import open_request_recorder
from algotrade.services.feedback.requests import MissingLike, record_missing
from algotrade.services.read.instruments.catalogue import feature_infos

log = logging.getLogger(__name__)
MEMORY = 512  # drafts remembered at most (the least recently used goes first)
KIND = "screen"
EDGE_KIND = "edge"


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
    seq: int = 1  # the ordinal of the latest draft request of the session
    closed: bool = False  # finalised: a later description starts a new session
    terms: frozenset[str] = frozenset()  # the answer's unresolved terms: ``choice_made`` subjects
    formulas: frozenset[str] = (
        frozenset()
    )  # its proposed formula names: accepted / skipped subjects


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

    def continue_session(self, session_id: str, user: str, doc_id: str) -> int | None:
        """The ``seq`` of the next draft request of an open session that is ``user``'s and
        ``doc_id``'s (the last draft *returned* plus one: a request that failed does not count);
        ``None`` (a new session starts) for one that is unknown, someone else's, another
        screen's, or already finalised."""
        with self._lock:
            item = self._items.get(session_id)
            if item is None or item.user != user or item.doc_id != doc_id or item.closed:
                return None
            self._items.move_to_end(session_id)
            return item.seq + 1

    def close(self, session_id: str, user: str, doc_id: str) -> None:
        """Note that the screen was finalised: the next description starts a new session."""
        with self._lock:
            item = self._items.get(session_id)
            if item is not None and item.user == user and item.doc_id == doc_id:
                self._items[session_id] = replace(item, closed=True)

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


def request_sink(given: FeedbackSink | None, live: bool, data_url: str) -> FeedbackSink:
    """The sink of the missing-feature request log: ``given`` (tests), else the recorder of
    ``feedback/feature_requests`` when the app is the served one, else one that records nothing."""
    if given is not None:
        return given
    return open_request_recorder(data_url) if live else NoFeedback()


def record_requests(
    sink: FeedbackSink,
    user: str,
    missing: Sequence[MissingLike],
    sentence: str,
    call_id: str | None,
    session_id: str,
) -> None:
    """The draft's ``missing`` items (as the server kept them) in the request log; nothing for a
    draft with none. Swallows its own failure, like every function here."""
    if not missing:
        return
    try:
        record_missing(sink, user, missing, sentence, call_id=call_id, draft_session_id=session_id)
    except Exception:
        log.exception("the missing-feature requests were not recorded")


def record_requested(
    sink: FeedbackSink,
    memory: DraftMemory,
    user: str,
    screener_id: str,
    sentence: str,
    document: Mapping[str, Any] | None,
    session_id: str | None = None,
) -> tuple[str, int]:
    """``draft_requested``, before the model is asked (a draft that fails leaves its trace):
    the ``draft_session_id`` and the ``seq`` of this request. ``session_id`` continues that
    session when it is open and ``user``'s for ``screener_id``, else a new one starts.
    ``document`` is the Builder's, whose criteria (the trader's edits since the last
    description) go in the payload as ``current_criteria``."""
    claimed = session_id
    try:
        seq = memory.continue_session(session_id, user, screener_id) if session_id else None
        if seq is None:
            session_id, seq = events.new_session_id(), 1
        payload: dict[str, Any] = {}
        if document is not None:
            payload["current_criteria"] = events.bounded(criteria_snapshot(document))
        if claimed and claimed != session_id:
            payload["claimed_session_id"] = claimed  # a restart lost it: chains.py relinks
        events.emit(
            sink, events.DRAFT_REQUESTED, str(session_id), user, KIND, screener_id,
            sentence=sentence, seq=seq, payload=payload,
        )  # fmt: skip
        return str(session_id), seq
    except Exception:
        log.exception("draft_requested not recorded")
        return events.new_session_id(), 1


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
    seq: int = 1,
    notes: Sequence[str] = (),
    terms: Sequence[str] = (),
    formulas: Sequence[str] = (),
) -> None:
    """``draft_returned`` (the model's criteria after validation, what it dropped and its
    notes) and the draft remembered for the save that follows, with the answer's unresolved
    ``terms`` and proposed ``formulas`` (the only subjects a later choice may name)."""
    try:
        version = events.catalogue_version(list(feature_infos(features)))  # the caller's fields
        draft_hash = events.document_hash(document)
        memory.put(
            session_id,
            Remembered(
                user, screener_id, copy.deepcopy(dict(document)), draft_hash, sentence,
                tuple(call_ids), version, prompt_version, seq=seq,
                terms=frozenset(terms), formulas=frozenset(formulas),
            ),
        )  # fmt: skip
        raw = document.get("criteria")
        payload = {
            "criteria": len(raw) if isinstance(raw, Mapping) else 0,
            "dropped": events.bounded(
                [{k: d[k] for k in ("id", "field", "reason") if k in d} for d in dropped],
                events.MAX_PART,
            ),
            "notes": events.bounded(list(notes), events.MAX_PART),
            "draft_criteria": events.bounded(criteria_snapshot(document)),
        }
        events.emit(
            sink, events.DRAFT_RETURNED, session_id, user, KIND, screener_id,
            call_ids=call_ids, catalogue_version=version, prompt_version=prompt_version,
            draft_hash=draft_hash, sentence=sentence, seq=seq, payload=payload,
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
    """The save events share one shape: the diff against the remembered draft, its hashes. A
    save does not end the session (the trader may describe again); finalising does. Two tabs on
    one screen share its session, last writer wins; each save is diffed against that session's own
    last draft."""
    if not session_id:
        return  # a hand-built screen: nothing to learn from
    try:
        content = events.document_hash(document)
        draft = memory.get(session_id, user, screener_id)
        claimed = session_id
        if (
            event == events.DRAFT_SAVED
            and draft is not None
            and not memory.saved(session_id, user, screener_id, content)
        ):
            return  # an autosave of the draft already recorded
        payload: dict[str, Any] = {
            "content_hash": content,
            "saved_criteria": events.bounded(criteria_snapshot(document)),  # the final criteria
        }
        if draft is None:
            payload["draft_unknown"] = True  # not remembered here, or not this user's: no diff
            payload["claimed_session_id"] = claimed  # chains.py links it if it is theirs
            session_id = ""  # never under a session id that is not theirs
        else:
            payload["diff"] = events.bounded(
                criteria_diff(draft.document, document), events.MAX_PART
            )
        events.emit(
            sink, event, session_id, user, KIND, screener_id,
            call_ids=draft.call_ids if draft else (),
            catalogue_version=draft.catalogue_version if draft else None,
            prompt_version=draft.prompt_version if draft else None,
            draft_hash=draft.draft_hash if draft else None,
            saved_hash=saved_hash or content,
            sentence=draft.sentence if draft else None,
            seq=draft.seq if draft else None,
            payload=payload,
        )  # fmt: skip
        if draft is not None and event == events.SCREEN_FINALISED:
            memory.close(session_id, user, screener_id)  # a later description is a new session
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


def record_choices(
    sink: FeedbackSink,
    memory: DraftMemory,
    session_id: str | None,
    user: str,
    screener_id: str,
    choices: Sequence[Any],
) -> None:
    """One ``choice_made`` / ``formula_accepted`` / ``formula_skipped`` row per choice
    (``subject``, ``picked`` in the payload) whose subject the session's last answer offered (an
    unresolved term, a proposed formula), for a session that is ``user``'s and
    ``screener_id``'s only (a session not remembered or not theirs records nothing). The
    ``event_id`` is a hash of the session, event, subject and pick, so a choice sent again with a
    later save is the same row. Call after the config write succeeded; never raises."""
    if not session_id or not choices:
        return
    try:
        draft = memory.get(session_id, user, screener_id)
        if draft is None:
            return
        for choice in choices:
            try:
                known = draft.terms if choice.event == events.CHOICE_MADE else draft.formulas
                if choice.subject not in known:
                    continue  # not something this answer offered: never a row under its session
                picked = choice.picked if choice.event == events.CHOICE_MADE else None
                row = events.row_of(
                    choice.event, session_id, user, KIND, screener_id,
                    call_ids=draft.call_ids, catalogue_version=draft.catalogue_version,
                    prompt_version=draft.prompt_version, draft_hash=draft.draft_hash,
                    sentence=draft.sentence, seq=draft.seq,
                    payload={"subject": choice.subject, "picked": picked},
                )  # fmt: skip
                key = f"{session_id}|{choice.event}|{choice.subject}|{picked}"
                row["event_id"] = hashlib.sha256(key.encode()).hexdigest()[:32]
                sink.submit(row)
            except Exception:
                log.exception("%s not recorded", choice.event)
    except Exception:
        log.exception("choices not recorded")


def record_edge_revised(
    sink: FeedbackSink,
    session_id: str | None,
    user: str,
    edge_id: str,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any],
) -> None:
    """``edge_revised``: call after the edge document was stored. ``before`` is the user's last
    stored revision (``None``: the first save) and ``after`` what was stored; nothing is recorded
    when their hashes are equal (an autosave; a TOML date and its string are the same). An edge
    has no remembered draft, so a ``session_id`` the client claims goes in the payload and is not
    linked (``chains.py`` never joins an edge claim to a screen), and the row is filed under a
    fresh session."""
    try:
        if before is not None and events.document_hash(before) == events.document_hash(after):
            return
        payload: dict[str, Any] = {
            "content_hash": events.document_hash(after),
            "diff": events.bounded(document_diff(before, after), events.MAX_PART),
            "saved_document": events.bounded(dict(after)),  # the edge as stored, clipped
        }
        if before is None:
            payload["first_revision"] = True
        if session_id:
            payload["claimed_session_id"] = session_id
        events.emit(
            sink, events.EDGE_REVISED, events.new_session_id(), user, EDGE_KIND, edge_id,
            draft_hash=events.document_hash(before) if before is not None else None,
            saved_hash=events.document_hash(after), payload=payload,
        )  # fmt: skip
    except Exception:
        log.exception("edge_revised not recorded")
