"""The site's feature catalogue: the code groups (``registry``) plus the expression features
of ``config/site/features/*/*.toml`` (loaded by the one settings loader), as one ``FeatureSet``;
and a user's catalogue: the site's plus ``config/users/<id>/features/*.toml`` (ADR 0023 step 4).

``site_features(configs)`` is what the ``rollups`` task, the read path (selections,
``FeatureView``), the selection catalogue and the feature catalogue use. It is built once per
config store (a bad formula fails here, naming the file, the feature and the position).
``user_features(configs, user)`` is read again on every call (a user edits their files while
the API runs) and rebuilt only when the definitions changed.
"""

from collections.abc import Sequence

from algotrade.config.site.features.definitions import FeatureDefinition
from algotrade.config.site.settings import SiteDocuments, load_features, load_user_features
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.registry import GROUPS, SUPERSEDED

_BUILT: dict[int, tuple[SiteDocuments, FeatureSet]] = {}  # by store identity (kept alive)
_USERS: dict[tuple[int, str], tuple[FeatureSet, str, FeatureSet]] = {}  # (site set, defs key)


def site_features(configs: SiteDocuments) -> FeatureSet:
    """Code groups + the site's expression features (built once per store)."""
    built = _BUILT.get(id(configs))
    if built is None or built[0] is not configs:
        built = (configs, FeatureSet.build(GROUPS, load_features(configs), SUPERSEDED))
        _BUILT[id(configs)] = built
    return built[1]


def with_user_features(site: FeatureSet, definitions: Sequence[FeatureDefinition]) -> FeatureSet:
    """``site`` plus these user definitions (reused while the definitions are unchanged)."""
    if not definitions:
        return site
    key = (id(site), definitions[0].owner or "")
    text = repr(definitions)
    cached = _USERS.get(key)
    if cached is not None and cached[0] is site and cached[1] == text:
        return cached[2]
    built = site.with_user(definitions)
    _USERS[key] = (site, text, built)
    return built


def user_features(configs: SiteDocuments, user: str, site: FeatureSet | None = None) -> FeatureSet:
    """``user``'s catalogue: ``site`` (default: ``configs``' site features) + their features."""
    base = site if site is not None else site_features(configs)
    return with_user_features(base, load_user_features(configs, user))
