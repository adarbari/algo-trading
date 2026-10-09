"""Whose configs a write touches, the authoring errors, and the writer the API opens.

A write is for a user the site registry declares (ADR 0040): ``author`` takes the registry as
a predicate (``Declared``; it does no I/O of its own), which the API always passes: a write
for an undeclared id is refused before it creates a config folder. The id must be valid and
never ``site`` (site presets change only by PR)."""

from collections.abc import Callable
from pathlib import Path

from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import AlgoTradeError, ConfigurationError
from algotrade.core.model.ids import validate_id
from algotrade.storage.configs.writer import ConfigWriter, FileConfigWriter

__all__ = [
    "ConfigWriter",
    "ConflictError",
    "Declared",
    "EdgeNotFoundError",
    "ScreenNotFoundError",
    "author",
    "open_writer",
]


class ConflictError(AlgoTradeError):
    """The write clashes with what exists (a screen already there, a version taken)."""


class ScreenNotFoundError(AlgoTradeError):
    """No such screen (no draft, no version, no preset) for this user."""


class EdgeNotFoundError(ScreenNotFoundError):
    """The user sees no such edge (a 404 like a missing screen)."""


Declared = Callable[[str], bool]  # whether the registry declares this user id


def author(user: str, declared: Declared | None = None) -> UserContext:
    """The user a write belongs to: a valid id, never the site, and (with ``declared``, the
    registry the API passes) one the registry declares: an unknown id is refused."""
    if user == SITE_USER:
        raise ConfigurationError("site presets change by PR, not through the API")
    who = UserContext(validate_id("user", user))
    if declared is not None and not declared(who.user_id):
        raise ConfigurationError(f"unknown user '{who.user_id}': not declared in users.toml")
    return who


def screen_id(name: str) -> str:
    return validate_id("screener", name)


def open_writer(config_dir: str | Path) -> ConfigWriter:
    """The config files under ``config_dir`` (``config.env.config_dir()`` by default)."""
    return FileConfigWriter(Path(config_dir))
