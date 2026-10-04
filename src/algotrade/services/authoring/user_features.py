"""Save a named user expression feature (``config/users/<u>/features/<theme>.toml``; ADR
0023, 0029). The user names it; it is checked with every other user feature against the
site catalogue (formula, types, no site name shadowed, never materialised) before the theme
file is replaced, so an invalid formula is never saved."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id
from algotrade.services.authoring.scope import author
from algotrade.services.features import catalogue
from algotrade.storage.configs.store import OverlayConfigStore
from algotrade.storage.configs.writer import ConfigWriter

DEFAULT_THEME = "builder"


@dataclass(frozen=True)
class SavedFeature:
    name: str
    field: str  # what screens select: feature.<name>
    theme: str
    dtype: str
    kind: str
    inputs: tuple[str, ...]


def save_user_feature(
    writer: ConfigWriter,
    user: str,
    name: str,
    definition: Mapping[str, Any],
    theme: str = DEFAULT_THEME,
) -> SavedFeature:
    """Add or replace ``user``'s feature ``name`` in ``theme``."""
    who = author(user).user_id
    validate_id("feature", name)
    validate_id("theme", theme)
    if not isinstance(definition, Mapping):
        raise ConfigurationError(f"{name}: a feature definition is a table")
    docs = {t: writer.load(who, "features", t) for t in writer.names(who, "features")}
    elsewhere = [t for t, d in docs.items() if t != theme and d and name in d]
    if elsewhere:
        raise ConfigurationError(f"{name}: already defined in {who}'s theme {elsewhere[0]!r}")
    updated = {**(docs.get(theme) or {}), name: dict(definition)}
    fs = catalogue(OverlayConfigStore(writer, {(who, "features", theme): updated}), who)
    expression = fs.expressions[name]
    writer.save_features(who, theme, updated)
    f = expression.feature
    return SavedFeature(name, f"feature.{name}", theme, f.dtype, f.kind, f.inputs)
