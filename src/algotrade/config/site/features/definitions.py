"""Expression-feature definitions (``config/site/features/<theme>.toml`` and a user's
``config/users/<id>/features/<theme>.toml``, ADR 0023 step 3): the typed ``FeatureDefinition``
per ``[<name>]`` section and the one loader that types them (``feature_definitions``). Split
from ``settings.py`` (at the file-length limit), which loads the documents through
``load_features`` / ``load_user_features``."""

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from algotrade.config.site.fields import Table, reject_secrets
from algotrade.core.model.errors import ConfigurationError

SCALARS = (bool, int, float, str)

FEATURE_KEYS = (
    "expr",
    "dtype",
    "unit",
    "description",
    "null_meaning",
    "kind",
    "valid_range",
    "categories",
    "materialise",
    "version",
    "params",
)
FEATURE_KINDS = ("expression", "label")
type ParamValue = float | str | bool


@dataclass(frozen=True)
class FeatureDefinition:
    """One ``[<name>]`` section of ``config/site/features/<theme>.toml``: an expression feature.

    ``expr`` is a formula over stored features (``group.column``), other expression features
    (by name) and ``params`` (named constants, by name); ``algotrade.features.expressions``
    parses, type checks and evaluates it. ``valid_range`` is ``[min, max]`` (``inf`` / ``-inf``:
    open); ``materialise`` stores it as ``rollups/instrument/<name>@v<version>`` (otherwise it
    is computed on read). The structure is typed here; the formula, dtype and unit are checked
    against the feature catalogue when the features are built.

    ``owner``: ``None`` for a site feature, else the user whose
    ``config/users/<owner>/features/<theme>.toml`` declares it (a user feature is never
    materialised)."""

    name: str
    theme: str
    expr: str
    dtype: str
    unit: str
    description: str
    null_meaning: str
    kind: str = "expression"
    valid_range: tuple[float | None, float | None] | None = None
    categories: tuple[str, ...] = ()
    materialise: bool = False
    version: int = 1
    params: Mapping[str, ParamValue] = field(default_factory=dict)
    owner: str | None = None

    @property
    def scope(self) -> str:
        """``site`` or ``user``."""
        return "site" if self.owner is None else "user"

    @property
    def where(self) -> str:
        return f"{features_dir(self.owner)}/{self.theme}.toml [{self.name}]"

    def canonical(self) -> dict[str, Any]:
        """What changes its values (for a config hash): formula, params, type and version."""
        return {
            "expr": " ".join(self.expr.split()),
            "params": dict(sorted(self.params.items())),
            "dtype": self.dtype,
            "kind": self.kind,
            "categories": list(self.categories),
            "version": self.version,
        }


def features_dir(owner: str | None) -> str:
    """Where a scope's expression features live (``config/site/features``,
    ``config/users/<owner>/features``)."""
    return "config/site/features" if owner is None else f"config/users/{owner}/features"


def _bound(value: Any) -> float | None:
    return None if value in (float("inf"), float("-inf")) else float(value)


def _valid_range(t: Table) -> tuple[float | None, float | None] | None:
    value = t.raw("valid_range")
    if value is None:
        return None
    numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
    if not isinstance(value, list) or len(value) != 2 or not numeric:
        raise ConfigurationError(
            f"{t.where} valid_range: expected [min, max] (inf: open), got {value!r}"
        )
    return (_bound(value[0]), _bound(value[1]))


def _params(t: Table) -> dict[str, ParamValue]:
    value = t.raw("params")
    if value is None:
        return {}
    if not isinstance(value, Mapping) or not all(isinstance(v, SCALARS) for v in value.values()):
        raise ConfigurationError(f"{t.where} params: expected a table of numbers, strings or bools")
    return dict(value)


def feature_definitions(
    docs: Mapping[str, Mapping[str, Any] | None], owner: str | None = None
) -> tuple[FeatureDefinition, ...]:
    """Every ``[<name>]`` of every ``features/<theme>.toml`` document, in file then key order.
    ``owner``: the user the documents belong to (``None``: the site). A user's documents may
    not hold secrets or ``materialise`` (user features are always computed on read)."""
    out = []
    for theme, doc in sorted(docs.items()):
        root = Table(doc, f"{features_dir(owner)}/{theme}.toml")
        if owner is not None and doc is not None:
            reject_secrets(doc, root.where)
        for name in root.names():
            t = root.table(name, FEATURE_KEYS)
            if owner is not None and t.raw("materialise") is not None:
                raise ConfigurationError(
                    f"{t.where} materialise: a user feature is always virtual (computed on "
                    "read); ask for a site feature to store it"
                )
            d = FeatureDefinition(name, theme, "", "", "", "", "", owner=owner)
            text = {
                k: t.text(k, "") for k in ("expr", "dtype", "unit", "description", "null_meaning")
            }
            missing = [k for k, v in text.items() if not v]
            if missing:
                raise ConfigurationError(f"{t.where}: missing {missing}")
            out.append(
                dataclasses.replace(
                    d,
                    **text,
                    kind=t.choice("kind", d.kind, FEATURE_KINDS),
                    valid_range=_valid_range(t),
                    categories=t.strings("categories", d.categories),
                    materialise=t.boolean("materialise", d.materialise),
                    version=t.integer("version", d.version, 1),
                    params=_params(t),
                )
            )
    return tuple(out)
