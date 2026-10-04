"""A user's rule screen (ADR 0029): read it (draft, versions, schedule, its preset pin), save
or discard the draft, finalise the draft into the next immutable version, and switch its
schedule. Finalise validates the whole screen as it would run (layers, selection, the
``ScreenSpec``, the catalogue incl. the user's features) and fails closed."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from algotrade.config.site.fields import reject_secrets
from algotrade.config.strategy.resolve import ResolvedConfig, config_document, parse_extends
from algotrade.config.strategy.schema import SCHEDULES
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.authoring.scope import (
    ConflictError,
    ScreenNotFoundError,
    author,
    screen_id,
)
from algotrade.services.configs import resolve_config, resolve_rule_draft
from algotrade.storage.configs.writer import ConfigWriter, VersionExistsError

# Set by the authoring flow, never by a draft: finalise numbers versions; the schedule is a
# separate switch.
MANAGED_KEYS = ("version", "schedule")


def validate(
    writer: ConfigWriter, user: UserContext, name: str, document: Mapping[str, Any]
) -> ResolvedConfig:
    """``document`` resolved as ``user``'s screen ``name``; a ``ConfigurationError`` (with
    its path) unless it is a valid rule screen."""
    return resolve_rule_draft(writer, name, user, document, writer.schedule(user.user_id, name))


def draft_document(name: str, document: Mapping[str, Any]) -> dict[str, Any]:
    """What a draft stores: the document with its id, without the managed keys."""
    if not isinstance(document, Mapping):
        raise ConfigurationError(f"{name}: a draft is a table")
    given = document.get("id", name)
    if given != name:
        raise ConfigurationError(f"{name}: the draft's id is {given!r}")
    return {"id": name} | {k: v for k, v in document.items() if k not in ("id", *MANAGED_KEYS)}


@dataclass(frozen=True)
class PresetPin:
    preset_id: str
    pinned: int | None  # the preset version the screen extends (None: unpinned)
    current: int | None  # the site preset's version now

    @property
    def rebase_available(self) -> bool:
        return self.pinned is not None and self.current is not None and self.current > self.pinned


@dataclass(frozen=True)
class ScreenDetail:
    screener_id: str
    user: str
    draft: dict[str, Any] | None
    draft_error: str | None  # why the draft would not finalise (None: it would)
    versions: list[int]
    latest: int | None
    schedule: str | None
    preset: PresetPin | None
    hash: str | None  # the latest version (or, with none, the site preset) resolved
    layers: list[str]
    resolved: dict[str, Any] | None
    error: str | None  # why that does not resolve (e.g. a stale pin: rebase)


def preset_pin(writer: ConfigWriter, document: Mapping[str, Any] | None) -> PresetPin | None:
    if not document or "extends" not in document:
        return None
    preset, pinned = parse_extends(document["extends"], "extends")
    site = config_document(writer.load, "site", preset)
    current = site[1].get("version") if site else None
    return PresetPin(preset, pinned, current if isinstance(current, int) else None)


def _error(fn: Any) -> str | None:
    try:
        fn()
    except ConfigurationError as exc:
        return str(exc)
    return None


def screen_detail(writer: ConfigWriter, user: str, name: str) -> ScreenDetail:
    """``user``'s screen ``name`` (or the site preset ``name`` they have not copied yet)."""
    who, name = author(user), screen_id(name)
    draft, versions = writer.draft(who.user_id, name), writer.versions(who.user_id, name)
    latest = writer.version(who.user_id, name, versions[-1]) if versions else None
    if draft is None and latest is None and config_document(writer.load, "site", name) is None:
        raise ScreenNotFoundError(f"no screen {name!r} for user {who.user_id!r}")
    owner = who if versions else UserContext(SITE_USER)
    resolved: ResolvedConfig | None = None
    try:
        resolved = resolve_config(writer, name, owner)
        error = None
    except ConfigurationError as exc:
        error = str(exc)
    draft_error = None
    if draft is not None:
        draft_error = _error(lambda: validate(writer, who, name, draft))
    return ScreenDetail(
        screener_id=name,
        user=who.user_id,
        draft=draft,
        draft_error=draft_error,
        versions=versions,
        latest=versions[-1] if versions else None,
        schedule=writer.schedule(who.user_id, name),
        preset=preset_pin(writer, draft if draft is not None else latest),
        hash=resolved.hash if resolved else None,
        layers=list(resolved.layers) if resolved else [],
        resolved=resolved.canonical() if resolved else None,
        error=error,
    )


@dataclass(frozen=True)
class ScreenVersion:
    version: int
    document: dict[str, Any]


def screen_versions(writer: ConfigWriter, user: str, name: str) -> list[ScreenVersion]:
    """Every finalised version of ``user``'s screen ``name``, oldest first."""
    who, name = author(user), screen_id(name)
    out = []
    for v in writer.versions(who.user_id, name):
        document = writer.version(who.user_id, name, v)
        out.append(ScreenVersion(v, document or {}))
    return out


def save_draft(
    writer: ConfigWriter, user: str, name: str, document: Mapping[str, Any]
) -> dict[str, Any]:
    """Store ``document`` as the working copy (autosave: not validated beyond being a
    serialisable, secret-free table; finalise validates). Returns what was stored."""
    who, name = author(user), screen_id(name)
    stored = draft_document(name, document)
    reject_secrets(stored, f"{who.user_id}/screeners/{name}/draft")
    writer.save_draft(who.user_id, name, stored)
    return stored


def discard_draft(writer: ConfigWriter, user: str, name: str) -> bool:
    who, name = author(user), screen_id(name)
    return writer.discard_draft(who.user_id, name)


@dataclass(frozen=True)
class Finalised:
    screener_id: str
    version: int
    hash: str


def finalise(writer: ConfigWriter, user: str, name: str) -> Finalised:
    """The draft becomes version ``latest + 1`` (immutable) and the draft is removed. Fails
    closed: nothing is written unless the screen resolves and validates exactly as it will
    run. Does not schedule (``set_schedule``)."""
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


def set_schedule(writer: ConfigWriter, user: str, name: str, schedule: str | None) -> str | None:
    """Switch ``user``'s finalised screen ``name`` on (``"nightly"``) or off (``None``)."""
    who, name = author(user), screen_id(name)
    if schedule is not None and schedule not in SCHEDULES:
        raise ConfigurationError(f"schedule must be one of {sorted(SCHEDULES)} or null")
    if not writer.versions(who.user_id, name):
        raise ScreenNotFoundError(f"{who.user_id}/{name}: finalise a version before scheduling")
    writer.set_schedule(who.user_id, name, schedule)
    return schedule
