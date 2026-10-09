"""A user's edges (ADR 0053 amendment 2026-10-09, ED8; ADR 0029 writes): copy an edge, save and
delete the user's own, and move the user's state about one (``[follow]``).

Everything lands in ``config/users/<id>/edges/<edge id>.toml`` through the writer, never the site's:
- ``copy_edge``: a new document ``extends = "<edge id>"`` (a site edge or the user's own); with
  ``as_version`` it is a trial of a replacement (``state = trial``, ``replaces`` the edge);
- ``save_edge``: the user's document replaced whole (the ``[follow]`` table is kept; the state
  has its own call). A site edge's id is never saved over: change it in a copy. It is resolved
  and typed exactly as the harness will read it (``config.edges.loading``) and written only if
  that succeeds: a clash fails closed and writes nothing;
- ``delete_edge``: archived (never erased); an id deleted once is not reused (its runs are keyed
  by it); an edge another of the user's extends is not deleted;
- ``set_state``: the transition (``TRANSITIONS``), and the labels the SERVER decides
  (``followed_against_verdict``, ``oos_viewed_during_tuning``, ``replaced_without_forward_test``,
  ``split_moved_after_viewing``): permanent, never removed, a warning and never a block. The state
  of a site edge the user has not copied is a file holding only ``[follow]``.
Publishing an edge site-wide is not a write: the admin reads its layered document as TOML
(``services/read/evaluation/versions.py``) and lands it in ``config/site/edges/`` by pull
request."""

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from algotrade.config.edges.document import Edge
from algotrade.config.edges.follow import KEY, LABELS, STATES, Follow
from algotrade.config.edges.loading import KIND, SITE, load_edges
from algotrade.config.site.fields import reject_secrets
from algotrade.config.site.settings import load_verdict
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id
from algotrade.core.time.calendar import sessions_between
from algotrade.services.authoring.scope import ConflictError, EdgeNotFoundError, author
from algotrade.storage.configs.writer import ConfigWriter

# state -> the states it may move to (a move to itself only restates it)
TRANSITIONS: Mapping[str, tuple[str, ...]] = {
    "researching": ("following", "rejected", "trial"),
    "following": ("retired", "researching"),
    "trial": ("following", "rejected", "researching"),
    "rejected": ("researching",),
    "retired": ("researching",),
}
NOT_WORKING = "not_working"  # the verdict a follow warns about (services.read verdict.NOT_WORKING)


@dataclass(frozen=True)
class StateChange:
    """What the caller asks: a new ``state`` (None: keep it), the ``reason`` a rejection or
    retirement needs, and whether to ``reveal_oos`` (show the copy's out-of-sample result)."""

    state: str | None = None
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
    return {e.id: e for e in load_edges(_Overlay(writer, user, edge_id, document), user)}[edge_id]


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
    user's), saved as its own document. ``as_version``: a trial of a replacement for the source
    (``[follow] state = trial``, ``replaces`` it, ``since`` today). ``ConflictError`` if the id is
    taken or was deleted; ``EdgeNotFoundError`` if the user sees no ``source_id``."""
    who, new_id = author(user).user_id, validate_id("edge", new_id)
    if source_id not in _visible(writer, who):
        raise _not_found(who, source_id)
    _refuse_taken(writer, who, new_id)
    document: dict[str, Any] = {"extends": source_id}
    if as_version:
        document[KEY] = {"state": "trial", "since": today, "replaces": source_id}
    _checked(writer, who, new_id, document)
    writer.save_user_document(who, KIND, new_id, document)
    return document


def save_edge(
    writer: ConfigWriter, user: str, edge_id: str, document: Mapping[str, Any]
) -> dict[str, Any]:
    """Replace (or create) the user's own edge document ``edge_id`` with ``document`` (its
    ``extends`` and settings; a ``[follow]`` table in it is ignored: the state has its own call).
    A site edge's id is refused (a copy under a new id changes it). If the user had seen the
    copy's out-of-sample result and the save moves its ``frozen_from``, the label
    ``split_moved_after_viewing`` is added. Returns the stored document."""
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
    stored = {k: v for k, v in copy.deepcopy(dict(document)).items() if k != KEY}
    stored.pop("id", None)  # the file's name is the id
    if previous is not None and previous.get(KEY) is not None:
        stored[KEY] = previous[KEY]
    before = _visible(writer, who).get(edge_id)
    after = _checked(writer, who, edge_id, stored)
    if (
        before is not None
        and before.follow.oos_revealed
        and before.frozen_from != after.frozen_from
    ):
        stored[KEY] = _follow_table(
            after.follow, labels=_with(after.follow.labels, "split_moved_after_viewing")
        )
    writer.save_user_document(who, KIND, edge_id, stored)
    return stored


def delete_edge(writer: ConfigWriter, user: str, edge_id: str, now: datetime | None = None) -> None:
    """Archive ``user``'s own document ``edge_id`` (its state about a site edge: reset to
    researching). ``EdgeNotFoundError`` if they have none; ``ConflictError`` if another of their
    edges extends it."""
    who, edge_id = author(user).user_id, validate_id("edge", edge_id)
    if _own(writer, who, edge_id) is None:
        raise _not_found(who, edge_id)
    extended_by = sorted(e.id for e in load_edges(writer, who) if e.extends == edge_id)
    if extended_by:
        raise ConflictError(f"{edge_id} is extended by {extended_by}: delete those first")
    writer.archive_user_document(who, KIND, edge_id, now or datetime.now(UTC))


def _with(labels: tuple[str, ...], *more: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys([*labels, *(m for m in more if m in LABELS)]))


def _follow_table(follow: Follow, **changes: Any) -> dict[str, Any]:
    """``follow`` as the TOML table (defaults left out), with ``changes`` over it."""
    values = {**follow.__dict__, **changes}
    out: dict[str, Any] = {"state": values["state"]}
    for key in ("since", "reason", "replaces"):
        if values[key]:
            out[key] = values[key]
    if values["labels"]:
        out["labels"] = list(values["labels"])
    if values["oos_revealed"]:
        out["oos_revealed"] = True
    return out


def _write_follow(writer: ConfigWriter, user: str, edge: Edge, table: dict[str, Any]) -> None:
    """Store ``table`` as the user's ``[follow]`` of ``edge``: in their own document, else in a
    file holding only it (a site edge they have not copied)."""
    document = _own(writer, user, edge.id)
    if document is None:
        document = {}
    document[KEY] = table
    writer.save_user_document(user, KIND, edge.id, document)


def set_state(
    writer: ConfigWriter,
    user: str,
    edge_id: str,
    change: StateChange,
    *,
    today: date,
    verdict: str | None = None,
) -> Follow:
    """Apply ``change`` to ``user``'s state about ``edge_id``; returns the new ``Follow``.

    Moves: ``TRANSITIONS`` (a move that is not one is a ``ConfigurationError``); rejecting needs a
    ``reason``. Labels the server adds, never removes: ``followed_against_verdict`` (following
    while ``verdict`` is ``not_working``), ``oos_viewed_during_tuning`` (revealing the
    out-of-sample result while not following), ``replaced_without_forward_test`` (a trial made the
    followed edge before ``forward_sessions`` sessions had passed). Replacing (a trial becomes
    following) retires the edge it replaces when the user follows it."""
    who, edge_id = author(user).user_id, validate_id("edge", edge_id)
    edge = _visible(writer, who).get(edge_id)
    if edge is None:
        raise _not_found(who, edge_id)
    follow = edge.follow
    state = change.state or follow.state
    if state not in STATES:
        raise ConfigurationError(f"state {state!r}: expected one of {list(STATES)}")
    if state != follow.state and state not in TRANSITIONS[follow.state]:
        raise ConfigurationError(
            f"{edge_id}: cannot go from {follow.state} to {state} "
            f"(from {follow.state}: {list(TRANSITIONS[follow.state])})"
        )
    reason = " ".join(change.reason.split())
    if state == "rejected" and not reason:
        raise ConfigurationError(f"{edge_id}: rejecting an edge needs a reason")
    labels = follow.labels
    if state == "following" and follow.state != "following" and verdict == NOT_WORKING:
        labels = _with(labels, "followed_against_verdict")
    if change.reveal_oos and not follow.oos_revealed and state != "following":
        labels = _with(labels, "oos_viewed_during_tuning")
    replaced = follow.replaces if follow.state == "trial" and state == "following" else None
    if replaced is not None and _forward_sessions(writer, follow.since, today) < _needed(writer):
        labels = _with(labels, "replaced_without_forward_test")
    moved = state != follow.state
    table = _follow_table(
        follow,
        state=state,
        since=today if moved else follow.since,
        reason=(reason if state in ("rejected", "retired") else "") if moved else follow.reason,
        replaces=(follow.replaces if state in ("trial", "following") else None)
        if moved
        else follow.replaces,
        labels=labels,
        oos_revealed=follow.oos_revealed or change.reveal_oos or state == "following",
    )
    _write_follow(writer, who, edge, table)
    if replaced is not None:
        _retire_replaced(writer, who, replaced, today)
    return _visible(writer, who)[edge_id].follow


def _forward_sessions(writer: ConfigWriter, since: date | None, today: date) -> int:
    return 0 if since is None else max(len(sessions_between(since, today)) - 1, 0)


def _needed(writer: ConfigWriter) -> int:
    return load_verdict(writer).forward_sessions


def _retire_replaced(writer: ConfigWriter, user: str, edge_id: str, today: date) -> None:
    """The edge a trial replaced is retired when the user follows it (a note of why)."""
    old = _visible(writer, user).get(edge_id)
    if old is None or old.follow.state != "following":
        return
    table = _follow_table(
        old.follow, state="retired", since=today, reason="replaced by a new version"
    )
    _write_follow(writer, user, old, table)
