"""A user's rule screen (ADR 0029): save or discard the draft, delete the screen (archived: off
the list and the nightly), and finalise the draft into the next immutable version (which puts
the screen on the nightly: ADR 0033). Finalise validates the whole screen as it would run
(layers, selection, the ``ScreenSpec``, the catalogue incl. the user's features) and fails
closed. Reading a screen (draft, versions, preset pin) is the read model's
(``services.read.screens.documents``)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from algotrade.config.site.fields import reject_secrets
from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.authoring.preferences import forget_screener
from algotrade.services.authoring.scope import (
    ConflictError,
    ScreenNotFoundError,
    author,
    screen_id,
)
from algotrade.services.configs import resolve_rule_draft
from algotrade.storage.configs.writer import ConfigWriter, VersionExistsError

# Set by the authoring flow, never by a draft: finalise numbers versions. ``schedule`` is a
# legacy key (every finalised screen runs nightly, ADR 0033): stripped, never written.
MANAGED_KEYS = ("version", "schedule")


def validate(
    writer: ConfigWriter, user: UserContext, name: str, document: Mapping[str, Any]
) -> ResolvedConfig:
    """``document`` resolved as ``user``'s screen ``name``; a ``ConfigurationError`` (with
    its path) unless it is a valid rule screen."""
    return resolve_rule_draft(writer, name, user, document)


def draft_document(name: str, document: Mapping[str, Any]) -> dict[str, Any]:
    """What a draft stores: the document with its id, without the managed keys."""
    if not isinstance(document, Mapping):
        raise ConfigurationError(f"{name}: a draft is a table")
    given = document.get("id", name)
    if given != name:
        raise ConfigurationError(f"{name}: the draft's id is {given!r}")
    return {"id": name} | {k: v for k, v in document.items() if k not in ("id", *MANAGED_KEYS)}


def save_draft(
    writer: ConfigWriter, user: str, name: str, document: Mapping[str, Any]
) -> dict[str, Any]:
    """Store ``document`` as the working copy (autosave: not validated beyond being a
    serialisable, secret-free table; finalise validates). Returns what was stored."""
    who, name = author(user), screen_id(name)
    if writer.draft(who.user_id, name) is None and not writer.versions(who.user_id, name):
        refuse_deleted_id(writer, who.user_id, name)
    stored = draft_document(name, document)
    reject_secrets(stored, f"{who.user_id}/screeners/{name}/draft")
    writer.save_draft(who.user_id, name, stored)
    return stored


def discard_draft(writer: ConfigWriter, user: str, name: str) -> bool:
    who, name = author(user), screen_id(name)
    return writer.discard_draft(who.user_id, name)


def refuse_deleted_id(writer: ConfigWriter, user: str, name: str) -> None:
    """A new screen never takes a deleted one's id: its runs, ideas and views are keyed by it."""
    if writer.was_deleted(user, name):
        raise ConflictError(f"{user}/{name}: a deleted screener used this name; choose another")


def delete_screen(writer: ConfigWriter, user: str, name: str, now: datetime | None = None) -> None:
    """Delete ``user``'s screen ``name``: its draft and every version are archived, so it leaves
    the list and the nightly (its stored runs stay), and the user's preferences forget it
    (``ideas.priority``, its views). A site preset changes only by PR: one the user has not
    copied is not theirs to delete (``ScreenNotFoundError``)."""
    who, name = author(user), screen_id(name)
    if not writer.delete_screen(who.user_id, name, now or datetime.now(UTC)):
        raise ScreenNotFoundError(f"{who.user_id}/{name}: no such screen of yours to delete")
    forget_screener(writer, who.user_id, name)


@dataclass(frozen=True)
class Finalised:
    screener_id: str
    version: int
    hash: str


def finalise(writer: ConfigWriter, user: str, name: str) -> Finalised:
    """The draft becomes version ``latest + 1`` (immutable) and the draft is removed. Fails
    closed: nothing is written unless the screen resolves and validates exactly as it will
    run. Finalising puts the screen on the nightly (ADR 0033)."""
    who, name = author(user), screen_id(name)
    draft = writer.draft(who.user_id, name)
    if draft is None:
        raise ScreenNotFoundError(f"{who.user_id}/{name}: no draft to finalise")
    versions = writer.versions(who.user_id, name)
    version = (versions[-1] if versions else 0) + 1
    document = draft_document(name, draft) | {"version": version}
    resolved = validate(writer, who, name, document)
    try:
        writer.add_version(who.user_id, name, version, document)
    except VersionExistsError as exc:
        raise ConflictError(f"{who.user_id}/{name}: {exc}; finalise again") from exc
    writer.discard_draft(who.user_id, name)
    return Finalised(name, version, resolved.hash)
