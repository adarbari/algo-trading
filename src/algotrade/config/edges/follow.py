"""What a user has decided about an edge (ADR 0053 amendment 2026-10-10: one status per edge,
following is a bookmark), typed into frozen dataclasses.

An edge has ONE status (``document.STATUSES``). On the user's own edge ``status`` is the user's
(researching, candidate, live, retired, rejected); on a site edge it is the site's. Following is
a bookmark on a SITE edge the user has not copied, nothing else:

    [follow]    ``since`` (the session the bookmark was made), ``labels`` (only
                ``followed_against_verdict``, decided by the server): the file
                ``config/users/<u>/edges/<site id>.toml`` holds nothing but this table
    [audit]     the server's bookkeeping of the user's OWN edge, never the browser's:
                ``status_since``, ``status_reason`` (why rejected or retired), ``replaces`` (a new
                version's edge id), ``labels`` (``AUDIT_LABELS``), ``oos_revealed`` (the user has
                seen the copy's out-of-sample result)

Which moves are allowed and which labels apply is ``services/authoring/edges.py``'s; this module
types and checks the shape. ``LEGACY`` and ``legacy_own`` read the old ``[follow]`` table
(``state``, ``reason``, ``replaces``, ``oos_revealed``) until ``scripts/migrate_edge_follows.py``
has rewritten every file; they go with that script."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id

KEY = "follow"
AUDIT = "audit"
AUDIT_LABELS = (
    "followed_against_verdict",
    "oos_viewed_during_tuning",
    "replaced_without_forward_test",
    "split_moved_after_viewing",
)
BOOKMARK_LABELS = ("followed_against_verdict",)
FOLLOW_KEYS = ("since", "labels")
AUDIT_KEYS = ("status_since", "status_reason", "replaces", "labels", "oos_revealed")
# The old ``[follow]`` state -> (the status of an own edge, whether a bookmark of a site edge
# keeps it: only ``following`` does). Removed once every file is migrated (PR 5).
LEGACY: Mapping[str, tuple[str, bool]] = {
    "researching": ("researching", False),
    "trial": ("candidate", False),
    "following": ("live", True),
    "rejected": ("rejected", False),
    "retired": ("retired", False),
}
LEGACY_KEYS = ("state", "reason", "replaces", "oos_revealed")


@dataclass(frozen=True)
class Follow:
    """The user's bookmark of a site edge: ``since`` (None: not followed) and its labels."""

    since: date | None = None
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class Audit:
    """The server's bookkeeping of the user's own edge (``[audit]``)."""

    status_since: date | None = None
    status_reason: str = ""
    replaces: str | None = None
    labels: tuple[str, ...] = ()
    oos_revealed: bool = False


def is_legacy(table: Any) -> bool:
    """``table`` (a ``[follow]``) is in the old shape: it has a ``state`` or another old key."""
    return isinstance(table, Mapping) and any(k in table for k in LEGACY_KEYS)


def _since(t: Table, key: str) -> date | None:
    """The date at ``key`` (TOML date or ISO text), None when absent."""
    raw = t.raw(key)
    if raw is None or type(raw) is date:
        return raw
    try:
        if isinstance(raw, str):
            return date.fromisoformat(raw)
    except ValueError:
        pass
    raise ConfigurationError(f"{t.where} {key}: expected a date (2026-04-01)")


def _labels(t: Table, allowed: tuple[str, ...]) -> tuple[str, ...]:
    labels = t.strings("labels", ())
    unknown = [x for x in labels if x not in allowed]
    if unknown:
        raise ConfigurationError(f"{t.where} labels: unknown {unknown} (known: {list(allowed)})")
    return tuple(dict.fromkeys(labels))


def parse_follow(doc: Mapping[str, Any], where: str) -> Follow:
    """The ``[follow]`` bookmark of ``doc`` (not followed when it has none). A table in the old
    shape (``state`` ...) is read through ``LEGACY``: only a state that kept the follow counts,
    and labels the bookmark has no use for are dropped."""
    if doc.get(KEY) is None:
        return Follow()
    legacy = is_legacy(doc[KEY])
    t = Table(doc, where).table(KEY, (*FOLLOW_KEYS, *LEGACY_KEYS) if legacy else FOLLOW_KEYS)
    since = _since(t, "since")
    if legacy:
        state = t.choice("state", "researching", tuple(LEGACY))
        labels = tuple(x for x in _labels(t, AUDIT_LABELS) if x in BOOKMARK_LABELS)
        return Follow(since, labels) if LEGACY[state][1] and since is not None else Follow()
    labels = _labels(t, BOOKMARK_LABELS)
    if since is None and labels:
        raise ConfigurationError(f"{t.where} since: required (a bookmark says when it was made)")
    return Follow(since, labels)


def parse_audit(doc: Mapping[str, Any], where: str) -> Audit:
    """The ``[audit]`` table of ``doc`` (the defaults when it has none)."""
    if doc.get(AUDIT) is None:
        return Audit()
    t = Table(doc, where).table(AUDIT, AUDIT_KEYS)
    replaces = t.text("replaces", "")
    return Audit(
        status_since=_since(t, "status_since"),
        status_reason=" ".join(t.text("status_reason", "").split()),
        replaces=validate_id("edge", replaces) if replaces else None,
        labels=_labels(t, AUDIT_LABELS),
        oos_revealed=t.boolean("oos_revealed", False),
    )


def legacy_own(table: Mapping[str, Any], where: str) -> tuple[str, dict[str, Any]]:
    """(status, ``[audit]`` table) of an own edge whose document still has the old ``[follow]``
    ``table``: researching -> researching, trial -> candidate, following -> live, rejected and
    retired as they are; the since, reason, replaces, labels and oos_revealed move to the audit."""
    t = Table({KEY: table}, where).table(KEY, (*FOLLOW_KEYS, *LEGACY_KEYS))
    status = LEGACY[t.choice("state", "researching", tuple(LEGACY))][0]
    audit: dict[str, Any] = {}
    since = _since(t, "since")
    if since is not None:
        audit["status_since"] = since
    reason = " ".join(t.text("reason", "").split())
    if reason:
        audit["status_reason"] = reason
    replaces = t.text("replaces", "")
    if replaces:
        audit["replaces"] = validate_id("edge", replaces)
    labels = _labels(t, AUDIT_LABELS)
    if labels:
        audit["labels"] = list(labels)
    if t.boolean("oos_revealed", False):
        audit["oos_revealed"] = True
    return status, audit
