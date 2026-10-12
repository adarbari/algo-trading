"""A user's edges (ADR 0053 amendment 2026-10-10, ED8; ADR 0029 writes): copy an edge, save and
delete the user's own, and move the user's status of one or bookmark a site edge.

Everything lands in ``config/users/<id>/edges/<edge id>.toml`` through the writer, never the site's:
- ``copy_edge``: a new document ``extends = "<edge id>"`` (a site edge or the user's own), a
  ``researching`` edge; with ``as_version`` a ``candidate`` that ``replaces`` the edge
  (``[audit]``);
- ``save_edge``: the user's document replaced whole (``status`` and ``[audit]`` are kept; the
  status has its own call; a ``[follow]`` table is refused). A site edge's id is never saved
  over: change it in a copy. It is resolved and typed exactly as the harness will read it
  (``config.edges.loading``) and written only if that succeeds: a clash fails closed and writes
  nothing;
- ``delete_edge``: archived (never erased); an id deleted once is not reused (its runs are keyed
  by it); an edge another of the user's extends is not deleted;
- ``set_status``: on an own edge the move (``TRANSITIONS``) and its ``[audit]``, with the labels
  the SERVER decides (``followed_against_verdict``, ``oos_viewed_during_tuning``,
  ``replaced_without_forward_test``, ``split_moved_after_viewing``): permanent, never removed,
  a warning and never a block; on a site edge the bookmark (a file holding only ``[follow]``,
  archived to unfollow);
- ``migrate_follows``: rewrites a user's files from the old ``[follow]`` states, idempotent.
Publishing an edge site-wide is not a write: the admin reads its layered document as TOML
(``services/read/evaluation/versions.py``) and lands it in ``config/site/edges/`` by pull
request."""

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from algotrade.config.edges.document import Edge
from algotrade.config.edges.follow import (
    AUDIT,
    AUDIT_LABELS,
    BOOKMARK_LABELS,
    Audit,
    is_legacy,
    legacy_own,
    parse_follow,
)
from algotrade.config.edges.follow import KEY as FOLLOW
from algotrade.config.edges.loading import (
    KIND,
    SITE,
    USER_STATUSES,
    edge_problems,
    load_edges,
)
from algotrade.config.site.fields import reject_secrets
from algotrade.config.site.settings import load_verdict
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id
from algotrade.core.time.calendar import sessions_between
from algotrade.services.authoring.scope import ConflictError, EdgeNotFoundError, author
from algotrade.storage.configs.writer import ConfigWriter

# status -> the statuses the user may move an own edge to (a move to itself only restates it)
TRANSITIONS: Mapping[str, tuple[str, ...]] = {
    "researching": ("candidate", "rejected"),
    "candidate": ("live", "rejected", "researching"),
    "live": ("retired", "candidate", "researching"),
    "rejected": ("researching",),
    "retired": ("researching",),
}
NOT_WORKING = "not_working"  # the verdict a follow warns about (services.read verdict.NOT_WORKING)


@dataclass(frozen=True)
class StatusChange:
    """What the caller asks. Of an own edge: a new ``status`` (None: keep it), the ``reason`` a
    rejection or retirement needs, and whether to ``reveal_oos`` (show the copy's out-of-sample
    result). Of a site edge: ``follow`` (True bookmarks it, False removes the bookmark)."""

    status: str | None = None
    follow: bool | None = None
    reason: str = ""
    reveal_oos: bool = False


class _Overlay:
    """``base`` with one more (or replaced) user edge document: what the layering would read
    if it were saved, to validate before anything is written."""

    def __init__(self, base: ConfigWriter, user: str, name: str, document: Mapping[str, Any]):
        self._base, self._user, self._name, self._doc = base, user, name, document

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None:
        if (scope, kind, name) == (self._user, KIND, self._name):
            return self._doc
        return self._base.load(scope, kind, name)

    def names(self, scope: str, kind: str) -> list[str]:
        found = self._base.names(scope, kind)
        if (scope, kind) == (self._user, KIND) and self._name not in found:
            return sorted([*found, self._name])
        return found


def _visible(writer: ConfigWriter, user: str) -> dict[str, Edge]:
    return {e.id: e for e in load_edges(writer, user)}


def _site_ids(writer: ConfigWriter) -> set[str]:
    return set(writer.names(SITE, KIND))


def _own(writer: ConfigWriter, user: str, edge_id: str) -> dict[str, Any] | None:
    found = writer.load(user, KIND, edge_id)
    return None if found is None else copy.deepcopy(dict(found))


def _checked(writer: ConfigWriter, user: str, edge_id: str, document: Mapping[str, Any]) -> Edge:
    """The edge ``document`` would be for ``user`` (a ``ConfigurationError`` with the file and
    key when it is not valid); nothing is written."""
    reject_secrets(document, f"users/{user}/edges/{edge_id}")
    overlay = _Overlay(writer, user, edge_id, document)
    found = {e.id: e for e in load_edges(overlay, user)}
    after = edge_problems(overlay, user)
    if edge_id not in found:  # the loader isolates a user's faulty file; a write must not
        raise ConfigurationError(after.get(edge_id, f"{edge_id}: not loadable"))
    broken = sorted(set(after) - set(edge_problems(writer, user)) - {edge_id})
    if broken:  # an edge that extends this one would silently drop off
        raise ConfigurationError(
            f"{edge_id}: this change would break {broken} (they extend it): "
            + "; ".join(after[b] for b in broken)
        )
    return found[edge_id]


def _not_found(user: str, edge_id: str) -> EdgeNotFoundError:
    return EdgeNotFoundError(f"{user} has no edge {edge_id!r}")


def _refuse_taken(writer: ConfigWriter, user: str, edge_id: str) -> None:
    if edge_id in _visible(writer, user) or _own(writer, user, edge_id) is not None:
        raise ConflictError(f"{user} already has an edge {edge_id!r}")
    if writer.was_archived(user, KIND, edge_id):
        raise ConflictError(f"{user}/{edge_id}: a deleted edge used this id; choose another")


def copy_edge(
    writer: ConfigWriter,
    user: str,
    source_id: str,
    new_id: str,
    *,
    today: date,
    as_version: bool = False,
) -> dict[str, Any]:
    """A new edge ``new_id`` of ``user`` that extends ``source_id`` (a site edge or one of the
    user's), saved as its own document, ``researching``. ``as_version``: a ``candidate`` that
    replaces the source (``[audit] replaces``, ``status_since`` today). ``ConflictError`` if the
    id is
    taken or was deleted; ``EdgeNotFoundError`` if the user sees no ``source_id``."""
    who, new_id = author(user).user_id, validate_id("edge", new_id)
    if source_id not in _visible(writer, who):
        raise _not_found(who, source_id)
    _refuse_taken(writer, who, new_id)
    document: dict[str, Any] = {"extends": source_id}
    if as_version:
        document["status"] = "candidate"
        document[AUDIT] = {"status_since": today, "replaces": source_id}
    _checked(writer, who, new_id, document)
    writer.save_user_document(who, KIND, new_id, document)
    return document


def save_edge(
    writer: ConfigWriter, user: str, edge_id: str, document: Mapping[str, Any]
) -> dict[str, Any]:
    """``save_edge_revision``'s stored document alone."""
    return save_edge_revision(writer, user, edge_id, document)[1]


def save_edge_revision(
    writer: ConfigWriter, user: str, edge_id: str, document: Mapping[str, Any]
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Replace (or create) the user's own edge document ``edge_id`` with ``document`` (its
    ``extends`` and settings; its ``status`` and ``[audit]`` are the stored ones: the status has
    its own call; a ``[follow]`` table is refused).
    A site edge's id is refused (a copy under a new id changes it). If the user had seen the
    copy's out-of-sample result and the save moves its ``frozen_from``, the label
    ``split_moved_after_viewing`` is added. Returns ``(previous, stored)``: the document the user
    had stored (``None``: a first save), read once, in the same call as the write, and the one
    stored."""
    who, edge_id = author(user).user_id, validate_id("edge", edge_id)
    if not isinstance(document, Mapping):
        raise ConfigurationError(f"{edge_id}: an edge document is a table")
    if edge_id in _site_ids(writer):
        raise ConflictError(
            f"{edge_id} is a site edge: copy it (extends = {edge_id!r}) under a new id to change it"
        )
    previous = _own(writer, who, edge_id)
    if previous is None:
        _refuse_taken(writer, who, edge_id)
    if FOLLOW in document:
        raise ConfigurationError(
            f"{edge_id}: an own edge has no [follow] table (a bookmark is of a site edge); "
            "its status has its own call"
        )
    before = _visible(writer, who).get(edge_id)
    stored = {k: v for k, v in copy.deepcopy(dict(document)).items() if k not in ("status", AUDIT)}
    stored.pop("id", None)  # the file's name is the id
    if before is not None:  # the status and its bookkeeping are the server's (``set_status``)
        if before.status != "researching":
            stored["status"] = before.status
        if table := _audit_table(before.audit):
            stored[AUDIT] = table
    after = _checked(writer, who, edge_id, stored)
    if before is not None and before.audit.oos_revealed and before.frozen_from != after.frozen_from:
        stored[AUDIT] = _audit_table(
            after.audit, labels=_with(after.audit.labels, "split_moved_after_viewing")
        )
    writer.save_user_document(who, KIND, edge_id, stored)
    return previous, stored


def delete_edge(writer: ConfigWriter, user: str, edge_id: str, now: datetime | None = None) -> None:
    """Archive ``user``'s own document ``edge_id`` (their bookmark of a site edge: removed).
    ``EdgeNotFoundError`` if they have none; ``ConflictError`` if another of their
    edges extends it."""
    who, edge_id = author(user).user_id, validate_id("edge", edge_id)
    if _own(writer, who, edge_id) is None:
        raise _not_found(who, edge_id)
    extended_by = sorted(e.id for e in load_edges(writer, who) if e.extends == edge_id)
    if extended_by:
        raise ConflictError(f"{edge_id} is extended by {extended_by}: delete those first")
    writer.archive_user_document(who, KIND, edge_id, now or datetime.now(UTC))


def _with(labels: tuple[str, ...], *more: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys([*labels, *(m for m in more if m in AUDIT_LABELS)]))


def _audit_table(audit: Audit, **changes: Any) -> dict[str, Any]:
    """``audit`` as the TOML table (defaults left out), with ``changes`` over it."""
    values = {**audit.__dict__, **changes}
    out: dict[str, Any] = {}
    for key in ("status_since", "status_reason", "replaces"):
        if values[key]:
            out[key] = values[key]
    if values["labels"]:
        out["labels"] = list(values["labels"])
    if values["oos_revealed"]:
        out["oos_revealed"] = True
    return out


def set_status(
    writer: ConfigWriter,
    user: str,
    edge_id: str,
    change: StatusChange,
    *,
    today: date,
    verdict: str | None = None,
) -> Edge:
    """Apply ``change`` to ``user``'s edge ``edge_id``; returns the edge as they now see it.

    A site edge: ``change.follow`` bookmarks or unbookmarks it (its status is the site's).
    An own edge: the status moves by ``TRANSITIONS`` (a move that is not one is a
    ``ConfigurationError``); rejecting needs a ``reason``. Labels the server adds, never removes:
    ``followed_against_verdict`` (following, or going live, while ``verdict`` is ``not_working``),
    ``oos_viewed_during_tuning`` (revealing the out-of-sample result while not live),
    ``replaced_without_forward_test`` (a candidate made live before ``forward_sessions`` sessions
    had passed). Making a candidate live retires the edge it replaces."""
    who, edge_id = author(user).user_id, validate_id("edge", edge_id)
    edge = _visible(writer, who).get(edge_id)
    if edge is None:
        raise _not_found(who, edge_id)
    if edge_id in _site_ids(writer):
        _set_follow(writer, who, edge, change, today, verdict)
    else:
        _set_own(writer, who, edge, change, today, verdict)
    return _visible(writer, who)[edge_id]


def _set_follow(
    writer: ConfigWriter,
    user: str,
    edge: Edge,
    change: StatusChange,
    today: date,
    verdict: str | None,
) -> None:
    if change.status is not None:
        raise ConfigurationError(
            f"{edge.id}: a site edge has the site's status; follow it, or copy it to set your own"
        )
    if change.follow is False:
        writer.archive_user_document(user, KIND, edge.id, datetime.now(UTC))
    elif change.follow and not edge.followed:
        labels = edge.follow.labels
        if verdict == NOT_WORKING:
            labels = tuple(dict.fromkeys([*labels, *BOOKMARK_LABELS]))
        table: dict[str, Any] = {"since": today}
        if labels:
            table["labels"] = list(labels)
        writer.save_user_document(user, KIND, edge.id, {FOLLOW: table})


def _set_own(
    writer: ConfigWriter,
    user: str,
    edge: Edge,
    change: StatusChange,
    today: date,
    verdict: str | None,
) -> None:
    if change.follow is not None:
        raise ConfigurationError(f"{edge.id}: only a site edge is followed; set its status")
    audit, current = edge.audit, edge.status
    status = change.status or current
    if status not in USER_STATUSES:
        raise ConfigurationError(f"status {status!r}: expected one of {list(USER_STATUSES)}")
    if status != current and status not in TRANSITIONS[current]:
        raise ConfigurationError(
            f"{edge.id}: cannot go from {current} to {status} "
            f"(from {current}: {list(TRANSITIONS[current])})"
        )
    reason = " ".join(change.reason.split())
    if status == "rejected" and not reason:
        raise ConfigurationError(f"{edge.id}: rejecting an edge needs a reason")
    labels = audit.labels
    if status == "live" and current != "live" and verdict == NOT_WORKING:
        labels = _with(labels, "followed_against_verdict")
    if change.reveal_oos and not audit.oos_revealed and status != "live":
        labels = _with(labels, "oos_viewed_during_tuning")
    replaced = audit.replaces if current == "candidate" and status == "live" else None
    if replaced is not None and _forward_sessions(audit.status_since, today) < _needed(writer):
        labels = _with(labels, "replaced_without_forward_test")
    moved = status != current
    table = _audit_table(
        audit,
        status_since=today if moved else audit.status_since,
        status_reason=(reason if status in ("rejected", "retired") else "")
        if moved
        else audit.status_reason,
        labels=labels,
        oos_revealed=audit.oos_revealed or change.reveal_oos or status == "live",
    )
    # Two files cannot change atomically: the old version is retired FIRST, so a failure between
    # the writes leaves a candidate and nothing live, never two versions live.
    if replaced is not None:
        _retire_replaced(writer, user, replaced, today)
    _write_status(writer, user, edge.id, status, table)


def _write_status(
    writer: ConfigWriter, user: str, edge_id: str, status: str, audit: dict[str, Any]
) -> None:
    """Store ``status`` and ``audit`` in the user's own document (an old ``[follow]`` in it is
    dropped: both come from it already), checked as the harness will read it."""
    document = _own(writer, user, edge_id) or {}
    document.pop(FOLLOW, None)
    document["status"] = status
    if audit:
        document[AUDIT] = audit
    else:
        document.pop(AUDIT, None)
    _checked(writer, user, edge_id, document)
    writer.save_user_document(user, KIND, edge_id, document)


def _forward_sessions(since: date | None, today: date) -> int:
    return 0 if since is None else max(len(sessions_between(since, today)) - 1, 0)


def _needed(writer: ConfigWriter) -> int:
    return load_verdict(writer).forward_sessions


def _retire_replaced(writer: ConfigWriter, user: str, edge_id: str, today: date) -> None:
    """The edge a new version replaced goes when it is made live: an own live edge is retired
    (a note of why), a followed site edge is unfollowed."""
    old = _visible(writer, user).get(edge_id)
    if old is None:
        return
    if edge_id in _site_ids(writer):
        if old.followed:
            writer.archive_user_document(user, KIND, edge_id, datetime.now(UTC))
    elif old.status == "live":
        table = _audit_table(
            old.audit,
            status_since=today,
            status_reason="replaced by a new version",
        )
        _write_status(writer, user, edge_id, "retired", table)


def migrate_follows(writer: ConfigWriter, user: str) -> dict[str, str]:
    """Rewrite ``user``'s edge files from the old ``[follow]`` states to one status and a
    bookmark (ADR 0053 amendment 2026-10-10), through the atomic writer; idempotent (a file
    already migrated is left alone). Returns what was done by edge id: ``followed``,
    ``unfollowed`` (archived) for a site edge's file, ``status <status>`` for an own edge.
    A file that cannot be read is skipped and named in the result with ``skipped: <reason>``."""
    who, done = author(user).user_id, {}
    site = _site_ids(writer)
    for name in writer.names(who, KIND):
        document = _own(writer, who, name)
        legacy = None if document is None else document.get(FOLLOW)
        if document is None or legacy is None or not is_legacy(legacy):
            continue
        where = f"config/users/{who}/edges/{name}.toml"
        try:
            if name in site:
                done[name] = _migrate_bookmark(writer, who, name, legacy, where)
            else:
                status, audit = legacy_own(legacy, where)
                document.pop(FOLLOW)
                document["status"] = status  # the old state wins over a stray status
                document.pop(AUDIT, None)
                if audit:
                    document[AUDIT] = audit
                writer.save_user_document(who, KIND, name, document)
                done[name] = f"status {document['status']}"
        except ConfigurationError as exc:
            done[name] = f"skipped: {exc}"
    return done


def _migrate_bookmark(
    writer: ConfigWriter, user: str, name: str, legacy: Mapping[str, Any], where: str
) -> str:
    follow = parse_follow({FOLLOW: legacy}, where)
    if follow.since is None:
        writer.archive_user_document(user, KIND, name, datetime.now(UTC))
        return "unfollowed"
    table: dict[str, Any] = {"since": follow.since}
    if follow.labels:
        table["labels"] = list(follow.labels)
    writer.save_user_document(user, KIND, name, {FOLLOW: table})
    return "followed"
