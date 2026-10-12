"""``DraftingEvent``: the Describe-it feedback events (``feedback/drafting_events``, ADR 0066)
a viewer may read, over a **date range** ending at the exchange date ``today`` (session-free, like
the usage read: a log is not a fact of one session).

The privacy rule is here, server side: a trader reads only their own rows, an admin all of them,
the role being the registry's (``Viewer.role``), never the client's. (Policy: an admin also sees
the formulas a trader accepted, across users: owner decision 2026-10-11, ADR 0066.) Newest
first, at most ``limit``. A column an older partition lacks reads as null."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from algotrade.config.site.users import Role
from algotrade.core.time.calendar import exchange_date
from algotrade.data.feedback import read_drafting_events
from algotrade.services.feedback.events import CALL_IDS_SEP
from algotrade.services.read.context import Stores
from algotrade.services.read.users.viewer import Viewer
from algotrade.services.read.values import to_scalar

MAX_LIMIT = 500
COLUMNS = (
    "event_id", "draft_session_id", "ts", "user", "doc_kind", "doc_id", "event", "call_ids",
    "catalogue_version", "prompt_version", "draft_hash", "saved_hash", "sentence", "payload", "seq",
)  # fmt: skip


@dataclass(frozen=True)
class DraftingEvent:
    """One event of a drafting session; ``call_ids`` the ``usage/llm_calls`` calls behind it,
    ``payload`` its small JSON text (a save's diff, a choice)."""

    event_id: str
    draft_session_id: str
    ts: datetime
    user: str
    doc_kind: str
    doc_id: str
    event: str
    call_ids: tuple[str, ...]
    catalogue_version: str | None
    prompt_version: str | None
    draft_hash: str | None
    saved_hash: str | None
    sentence: str | None
    payload: str | None
    seq: int | None  # the 1-based ordinal of the draft request in its session


def load_drafting_events(
    ctx: Stores,
    viewer: Viewer,
    since: date,
    limit: int = 100,
    today: date | None = None,
) -> tuple[DraftingEvent, ...]:
    """The events from ``since`` to ``today`` (default: the exchange date now) that ``viewer``
    may read, newest first, at most ``limit`` (capped at ``MAX_LIMIT``)."""
    today = today or exchange_date(datetime.now(UTC))
    stored = read_drafting_events(ctx.reader, since, today)
    if stored is None or stored.empty:
        return ()
    frame = stored.reindex(columns=list(COLUMNS))  # older partitions may lack a column
    if viewer.role != Role.ADMIN.value:
        frame = frame[frame["user"] == viewer.user_id]
    newest = frame.sort_values("ts", ascending=False).head(max(0, min(limit, MAX_LIMIT)))
    return tuple(_event(r) for r in newest.to_dict("records"))


def _text(value: Any) -> str | None:
    scalar = to_scalar(value)
    return None if scalar is None else str(scalar)


def _event(row: Mapping[Any, Any]) -> DraftingEvent:
    calls = _text(row["call_ids"])
    seq = row["seq"]
    return DraftingEvent(
        event_id=str(row["event_id"]),
        draft_session_id=str(row["draft_session_id"]),
        ts=pd.Timestamp(row["ts"]).to_pydatetime(),
        user=str(row["user"]),
        doc_kind=str(row["doc_kind"]),
        doc_id=str(row["doc_id"]),
        event=str(row["event"]),
        call_ids=tuple(calls.split(CALL_IDS_SEP)) if calls else (),
        catalogue_version=_text(row["catalogue_version"]),
        prompt_version=_text(row["prompt_version"]),
        draft_hash=_text(row["draft_hash"]),
        saved_hash=_text(row["saved_hash"]),
        sentence=_text(row["sentence"]),
        payload=_text(row["payload"]),
        seq=None if pd.isna(seq) else int(seq),
    )
