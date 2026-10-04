"""Whose configs a write touches, the authoring errors, and the writer the API opens.

Phase 0 users are plain labels (``?user=``; no auth until identity arrives, ADR 0029): a
label must be a valid id and never ``site`` (site presets change only by PR)."""

from pathlib import Path

from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import AlgoTradeError, ConfigurationError
from algotrade.core.model.ids import validate_id
from algotrade.storage.configs.writer import ConfigWriter, FileConfigWriter

__all__ = ["ConfigWriter", "ConflictError", "ScreenNotFoundError", "author", "open_writer"]


class ConflictError(AlgoTradeError):
    """The write clashes with what exists (a screen already there, a version taken)."""


class ScreenNotFoundError(AlgoTradeError):
    """No such screen (no draft, no version, no preset) for this user."""


def author(user: str) -> UserContext:
    """The user a write belongs to: a valid id, never the site."""
    if user == SITE_USER:
        raise ConfigurationError("site presets change by PR, not through the API")
    return UserContext(validate_id("user", user))


def screen_id(name: str) -> str:
    return validate_id("screener", name)


def open_writer(config_dir: str | Path) -> ConfigWriter:
    """The config files under ``config_dir`` (``config.env.config_dir()`` by default)."""
    return FileConfigWriter(Path(config_dir))
