"""A user's rule screens as the Builder reads them (ADR 0029): the screens they own
(``ScreenListing``: finalised and draft-only), one screen's working state (``ScreenDetail``:
its draft and whether it would finalise, its versions, the site preset it is pinned to, the
working copy resolved through its layers) and its finalised versions (``ScreenVersion``).

Configs, not session data: what is stored now under ``config/users/<id>/screeners/``, read
through the ``ConfigStore`` (``services.authoring`` writes it). The user is ``ctx.user``; the
site user owns no screens (presets change only by pull request)."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from algotrade.config.strategy.resolve import ResolvedConfig, config_document, parse_extends
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id
from algotrade.services.configs import resolve_config, resolve_rule_draft
from algotrade.services.read.context import Stores
from algotrade.storage.configs.files import SCREENERS
from algotrade.storage.configs.store import ConfigStore

FINAL = "FINAL"  # has a finalised version
DRAFT = "DRAFT"  # a draft only


@dataclass(frozen=True)
class PresetPin:
    """The site preset a screen extends: ``pinned``, the preset version it extends (None:
    unpinned, or a preset not copied yet); ``current``, the preset's version now;
    ``rebase_available``: the preset moved on since the pinned version."""

    preset_id: str
    pinned: int | None
    current: int | None
    rebase_available: bool


def _pin(preset_id: str, pinned: int | None, current: int | None) -> PresetPin:
    moved = pinned is not None and current is not None and current > pinned
    return PresetPin(preset_id, pinned, current, moved)


@dataclass(frozen=True)
class ScreenDetail:
    """One screen of the user (or a site preset they have not copied yet). ``draft_error``: why
    the draft would not finalise (None: it would); ``error``: why the latest version (or,
    with none, the site preset) does not resolve (e.g. a stale pin: rebase); ``working``: the
    rule keys (criteria, flags, ...) of the working copy resolved through its layers (the draft
    when it resolves, else the latest version, else the preset): what the Builder edits."""

    screener_id: str
    user: str
    draft: dict[str, Any] | None
    draft_error: str | None
    versions: tuple[int, ...]
    latest: int | None
    preset: PresetPin | None
    error: str | None
    working: dict[str, Any] | None


@dataclass(frozen=True)
class ScreenListing:
    """One screen of the user. ``status``: FINAL (has a finalised version) or DRAFT (a draft
    only); ``has_draft``: a working copy exists (beside a finalised version too);
    ``preset_id``: the site preset it extends (the draft's, else the latest version's)."""

    screener_id: str
    status: str
    latest: int | None
    has_draft: bool
    preset_id: str | None


@dataclass(frozen=True)
class ScreenVersion:
    version: int
    document: dict[str, Any]


def preset_pin(configs: ConfigStore, document: Mapping[str, Any] | None) -> PresetPin | None:
    if not document or "extends" not in document:
        return None
    preset, pinned = parse_extends(document["extends"], "extends")
    site = config_document(configs.load, "site", preset)
    current = site[1].get("version") if site else None
    return _pin(preset, pinned, current if isinstance(current, int) else None)


def _uncopied(name: str, site: tuple[str, Mapping[str, Any]] | None) -> PresetPin | None:
    """The pin of a site rule-screen preset the user has not copied yet: the preset itself,
    at its current version (``pinned`` None: nothing is based on it yet)."""
    version = site[1].get("version") if site and site[0] == SCREENERS else None
    return _pin(name, None, version) if isinstance(version, int) else None


def screen_detail(configs: ConfigStore, user: UserContext, name: str) -> ScreenDetail | None:
    """``user``'s screen ``name`` (or the site preset ``name`` they have not copied yet);
    ``None`` when there is neither."""
    name = validate_id("screener", name)
    if user.user_id == SITE_USER:
        return None
    who = user.user_id
    draft, versions = configs.draft(who, name), configs.versions(who, name)
    latest = configs.version(who, name, versions[-1]) if versions else None
    site = config_document(configs.load, "site", name) if draft is None and latest is None else None
    if draft is None and latest is None and site is None:
        return None
    resolved: ResolvedConfig | None = None
    try:
        resolved = resolve_config(configs, name, user if versions else UserContext(SITE_USER))
        error = None
    except ConfigurationError as exc:
        error = str(exc)
    draft_error = None
    working = dict(resolved.config.rules) if resolved else None
    if draft is not None:
        try:
            working = dict(resolve_rule_draft(configs, name, user, draft).config.rules)
        except ConfigurationError as exc:
            draft_error = str(exc)
    return ScreenDetail(
        screener_id=name,
        user=who,
        draft=draft,
        draft_error=draft_error,
        versions=tuple(versions),
        latest=versions[-1] if versions else None,
        preset=preset_pin(configs, draft if draft is not None else latest) or _uncopied(name, site),
        error=error,
        working=working,
    )


def screen_listings(configs: ConfigStore, user: UserContext) -> tuple[ScreenListing, ...]:
    """Every screen of ``user``: the finalised ones and the draft-only ones, sorted by id."""
    if user.user_id == SITE_USER:
        return ()
    who = user.user_id
    drafts = set(configs.drafts(who))
    out = []
    for name in sorted({*configs.names(who, SCREENERS), *drafts}):
        versions = configs.versions(who, name)
        draft = configs.draft(who, name) if name in drafts else None
        latest = configs.version(who, name, versions[-1]) if versions else None
        pin = preset_pin(configs, draft if draft is not None else latest)
        out.append(
            ScreenListing(
                screener_id=name,
                status=FINAL if versions else DRAFT,
                latest=versions[-1] if versions else None,
                has_draft=name in drafts,
                preset_id=pin.preset_id if pin else None,
            )
        )
    return tuple(out)


def screen_versions(
    configs: ConfigStore, user: UserContext, name: str
) -> tuple[ScreenVersion, ...]:
    """Every finalised version of ``user``'s screen ``name``, oldest first."""
    name = validate_id("screener", name)
    if user.user_id == SITE_USER:
        return ()
    who = user.user_id
    return tuple(
        ScreenVersion(v, configs.version(who, name, v) or {}) for v in configs.versions(who, name)
    )


def load_screen_listings(ctx: Stores) -> tuple[ScreenListing, ...]:
    """The screens ``ctx.user`` owns (``screen_listings``)."""
    return screen_listings(ctx.configs, ctx.user)


def load_screen_detail(ctx: Stores, screener_id: str) -> ScreenDetail | None:
    """``ctx.user``'s screen ``screener_id`` (``screen_detail``); ``None``: no such screen."""
    return screen_detail(ctx.configs, ctx.user, screener_id)


def load_screen_versions(ctx: Stores, screener_id: str) -> tuple[ScreenVersion, ...]:
    """The finalised versions of ``ctx.user``'s screen ``screener_id``, oldest first."""
    return screen_versions(ctx.configs, ctx.user, screener_id)
