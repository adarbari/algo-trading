"""Save a user's preferences (``config/users/<u>/preferences.toml``; ADR 0029): today the
Ideas screener priority, ``ideas.priority`` (screener ids, best first). Every id must be a
screen the user can run (their own or a site preset) and listed once, so a stale or mistyped
id is never saved."""

from collections.abc import Sequence
from typing import Any

from algotrade.config.user import SITE_USER
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.authoring.scope import author, screen_id
from algotrade.storage.configs.writer import ConfigWriter

PREFERENCES = "preferences"


def save_ideas_priority(writer: ConfigWriter, user: str, priority: Sequence[str]) -> list[str]:
    """Replace ``user``'s ``ideas.priority`` (other preferences are kept); returns it."""
    who = author(user).user_id
    ids = [screen_id(i) for i in priority]
    if len(set(ids)) != len(ids):
        raise ConfigurationError("ideas.priority lists a screener twice")
    known = {*writer.names(who, "screeners"), *writer.names(SITE_USER, "screeners")}
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise ConfigurationError(f"ideas.priority: not your screeners or site presets: {unknown}")
    current: dict[str, Any] = dict(writer.load(who, PREFERENCES, PREFERENCES) or {})
    current["ideas"] = {**dict(current.get("ideas") or {}), "priority": ids}
    writer.save_preferences(who, current)
    return ids
