"""Copy a site rule-screen preset into a user screen pinned to the preset's version
(``extends = "<preset>@N"``), and rebase a pinned screen onto the preset's current version.
Both write the draft only (the user finalises), after validating it fails closed."""

from typing import Any

from algotrade.config.strategy.resolve import config_document, parse_extends
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.authoring.scope import (
    ConflictError,
    ScreenNotFoundError,
    author,
    screen_id,
)
from algotrade.services.authoring.screens import MANAGED_KEYS, validate
from algotrade.storage.configs.writer import ConfigWriter


def _preset_version(writer: ConfigWriter, preset: str) -> int:
    found = config_document(writer.load, "site", screen_id(preset))
    if found is None or found[0] != "screeners":
        raise ScreenNotFoundError(f"no site rule-screen preset {preset!r}")
    version = found[1].get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ConfigurationError(f"site/screeners/{preset}: a preset carries version = N")
    return version


def copy_preset(writer: ConfigWriter, user: str, name: str, preset: str) -> dict[str, Any]:
    """A new draft ``name`` for ``user`` extending ``preset`` at its current version.
    ``ConflictError`` if ``user`` already has a screen or config ``name``."""
    who, name = author(user), screen_id(name)
    exists = (
        writer.draft(who.user_id, name) is not None
        or writer.versions(who.user_id, name)
        or config_document(writer.load, who.user_id, name) is not None
    )
    if exists:
        raise ConflictError(f"{who.user_id} already has a config {name!r}")
    draft: dict[str, Any] = {"id": name, "extends": f"{preset}@{_preset_version(writer, preset)}"}
    validate(writer, who, name, draft)
    writer.save_draft(who.user_id, name, draft)
    return draft


def rebase(writer: ConfigWriter, user: str, name: str) -> dict[str, Any]:
    """Re-pin ``user``'s screen ``name`` (its draft, else its latest version) to the
    preset's current version, keeping the user's overrides; saved as the draft once it
    validates on the new version (a clash fails closed and writes nothing)."""
    who, name = author(user), screen_id(name)
    base = writer.draft(who.user_id, name)
    if base is None:
        versions = writer.versions(who.user_id, name)
        if not versions:
            raise ScreenNotFoundError(f"no screen {name!r} for user {who.user_id!r}")
        base = writer.version(who.user_id, name, versions[-1]) or {}
    if "extends" not in base:
        raise ConfigurationError(f"{who.user_id}/{name}: does not extend a preset")
    preset, _ = parse_extends(base["extends"], f"{who.user_id}/{name}")
    draft = {k: v for k, v in base.items() if k not in MANAGED_KEYS}
    draft["extends"] = f"{preset}@{_preset_version(writer, preset)}"
    validate(writer, who, name, draft)
    writer.save_draft(who.user_id, name, draft)
    return draft
