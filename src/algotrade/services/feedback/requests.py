"""One missing-feature request of Describe it as a row of ``feedback/feature_requests`` (ADR 0066
amendment 2026-10-11) and ``record_missing``, which turns a draft's ``missing`` items into rows and
hands them to a ``FeedbackSink`` without ever raising: a request that cannot be built or queued is
dropped (logged) and the draft goes on.

A row holds the **span** of the sentence the request covers (clipped to ``MAX_SPAN``), never the
sentence, and only when the span really is a piece of that sentence: the model proposes it, so one
that is not a substring of the sentence (invented, paraphrased) is stored as null. ``ref`` is the
identity of what was asked for, the backlog key else the new slug, never derived from free text
(an item with neither is skipped); ``key`` is set only for a backlog item, ``new_slug`` only for a
request the backlog does not know (an admin sees those as unmapped and a PR merges them into a key
or alias). The items are anything
with ``key``, ``new_key_slug``, ``span``, ``closest`` and ``feasibility`` (``MissingFeature`` of
the drafting answer), so this package imports nothing of ``services/drafting``."""

import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, Protocol

import pandas as pd

from algotrade.core.model.completion import clip
from algotrade.services.feedback.events import FeedbackSink

MAX_SPAN = 300  # characters of the sentence's span kept
CLOSEST_SEP = ","
FEASIBILITY = ("ROLLUP_FROM_STORED", "NEEDS_SOURCE", "UNCLEAR")

log = logging.getLogger(__name__)


class MissingLike(Protocol):
    """What ``record_missing`` reads of an item (``drafting.gaps.MissingFeature`` has them)."""

    @property
    def key(self) -> str | None: ...
    @property
    def new_key_slug(self) -> str | None: ...
    @property
    def span(self) -> str: ...
    @property
    def closest(self) -> tuple[str, ...]: ...
    @property
    def feasibility(self) -> str: ...


def _fold(text: str) -> str:
    return " ".join((text or "").split())


def span_of(span: str, sentence: str) -> str | None:
    """``span`` (whitespace folded, clipped to ``MAX_SPAN``) when it is a piece of ``sentence``
    (compared ignoring case and whitespace), else ``None``: what the sentence did not say is not
    stored."""
    folded = _fold(span)
    if not folded or folded.casefold() not in _fold(sentence).casefold():
        return None
    return clip(folded, MAX_SPAN)


def request_row(
    user: str,
    item: MissingLike,
    sentence: str,
    *,
    at: datetime | None = None,
    call_id: str | None = None,
    draft_session_id: str | None = None,
) -> dict[str, Any] | None:
    """The row of one request (the point-in-time columns are stamped by the recorder), ``None``
    for an item that names neither a key nor a slug."""
    key = (item.key or "").strip() or None
    slug = None if key else (item.new_key_slug or "").strip() or None
    ref = key or slug
    if ref is None:
        return None
    return {
        "ts": at or datetime.now(UTC),
        "user": user,
        "ref": ref,
        "key": key,
        "new_slug": slug,
        "feasibility": item.feasibility if item.feasibility in FEASIBILITY else "UNCLEAR",
        "span": span_of(item.span, sentence),
        "closest": CLOSEST_SEP.join(c for c in item.closest if c) or None,
        "call_id": call_id or None,
        "draft_session_id": draft_session_id or None,
    }


def record_missing(
    sink: FeedbackSink,
    user: str,
    items: Iterable[MissingLike],
    sentence: str,
    *,
    call_id: str | None = None,
    draft_session_id: str | None = None,
    at: datetime | None = None,
) -> int:
    """Queue one row per item of a draft's ``missing`` (the request log, one count per user, key
    and day is the table's key); the number of rows queued. Never raises."""
    queued = 0
    try:
        at = at or datetime.now(UTC)
        for item in items:
            try:
                row = request_row(
                    user, item, sentence, at=at, call_id=call_id, draft_session_id=draft_session_id
                )
                if row is not None and sink.submit(row):
                    queued += 1
            except Exception:
                log.exception("a missing-feature request was not recorded")
    except Exception:
        log.exception("missing-feature requests were not recorded")
    return queued


def null_spans(frame: pd.DataFrame, keep: pd.Series | None = None) -> tuple[pd.DataFrame, int]:
    """``frame`` of ``feedback/feature_requests`` with every ``span`` nulled (except the rows of
    ``keep``, a boolean mask) and the number of rows changed: the retention edit, in the form the
    feedback retention command takes (``services/feedback/retention.py``)."""
    mask = frame["span"].notna()
    if keep is not None:
        mask &= ~keep
    out = frame.copy()
    out["span"] = out["span"].astype("object")
    out.loc[mask, "span"] = None
    return out, int(mask.sum())


def erase_user(frame: pd.DataFrame, user: str, token: str) -> tuple[pd.DataFrame, int]:
    """``frame`` with every row of ``user`` stripped of its span and its user id (``token``
    takes its place) and the number of rows changed: the erase edit."""
    mask = frame["user"] == user
    out, _ = null_spans(frame, ~mask)
    out["user"] = out["user"].astype("object")
    out.loc[mask, "user"] = token
    return out, int(mask.sum())


__all__ = ["MissingLike", "erase_user", "null_spans", "record_missing", "request_row", "span_of"]
