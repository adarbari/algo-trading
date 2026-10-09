"""What a user has decided about an edge (ADR 0053 amendment 2026-10-09, ED8): the ``[follow]``
table of the user's own edge document, typed into a frozen ``Follow``.

    state         researching (default) | following | rejected | retired | trial
    since         the session the state began (a date)
    reason        why it was rejected or retired
    replaces      a new version's trial: the edge id (v1) it would replace
    labels        permanent, decided by the server (``LABELS``), never by the browser
    oos_revealed  the user has seen the copy's out-of-sample result

The table is the user's own state, never inherited by a copy and never part of the document
an admin publishes. Which transitions are allowed and which labels apply is
``services/authoring/edges.py``'s; this module only types and checks the shape."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id

KEY = "follow"
STATES = ("researching", "following", "rejected", "retired", "trial")
LABELS = (
    "followed_against_verdict",
    "oos_viewed_during_tuning",
    "replaced_without_forward_test",
    "split_moved_after_viewing",
)
FOLLOW_KEYS = ("state", "since", "reason", "replaces", "labels", "oos_revealed")


@dataclass(frozen=True)
class Follow:
    state: str = "researching"
    since: date | None = None
    reason: str = ""
    replaces: str | None = None
    labels: tuple[str, ...] = ()
    oos_revealed: bool = False


def parse_follow(doc: Mapping[str, Any], where: str) -> Follow:
    """The ``[follow]`` table of ``doc`` (the defaults when it has none)."""
    if doc.get(KEY) is None:
        return Follow()
    t = Table(doc, where).table(KEY, FOLLOW_KEYS)
    labels = t.strings("labels", ())
    unknown = [x for x in labels if x not in LABELS]
    if unknown:
        raise ConfigurationError(f"{t.where} labels: unknown {unknown} (known: {list(LABELS)})")
    raw = t.raw("since")
    if raw is not None and type(raw) is not date:
        try:
            raw = date.fromisoformat(raw) if isinstance(raw, str) else raw
        except ValueError:
            raw = None
        if type(raw) is not date:
            raise ConfigurationError(f"{t.where} since: expected a date (2026-04-01)")
    replaces = t.text("replaces", "")
    return Follow(
        state=t.choice("state", "researching", STATES),
        since=raw,
        reason=" ".join(t.text("reason", "").split()),
        replaces=validate_id("edge", replaces) if replaces else None,
        labels=tuple(dict.fromkeys(labels)),
        oos_revealed=t.boolean("oos_revealed", False),
    )
