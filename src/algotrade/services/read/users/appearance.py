"""``Appearance``: the user's stored theme choice (ADR 0085 decision 6): ``[appearance] theme``
of their ``preferences.toml``, one of ``light`` / ``dark`` / ``system``. Per user, read through
the ``ConfigStore`` and never from ``Viewer`` (which is in memory), and session-free (a
``Stores``: a fresh store still has it); a missing file, a missing key or a malformed value
reads as ``system`` (the OS decides), never as an error. Written by
``services.authoring.preferences.save_appearance``."""

from dataclasses import dataclass

from algotrade.services.read.context import Stores
from algotrade.services.read.screens.views import PREFERENCES

APPEARANCE = "appearance"
THEMES = ("light", "dark", "system")
DEFAULT_THEME = "system"


@dataclass(frozen=True)
class Appearance:
    theme: str  # one of THEMES


def load_appearance(ctx: Stores) -> Appearance:
    """The theme ``ctx.user`` chose, else ``system`` (also for a value that is not a theme)."""
    doc = ctx.configs.load(ctx.user.user_id, PREFERENCES, PREFERENCES) or {}
    table = doc.get(APPEARANCE)
    theme = table.get("theme") if isinstance(table, dict) else None
    return Appearance(theme if isinstance(theme, str) and theme in THEMES else DEFAULT_THEME)
