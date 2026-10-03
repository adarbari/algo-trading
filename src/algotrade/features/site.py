"""The site's feature catalogue: the code groups (``registry``) plus the expression features
of ``config/site/features/*.toml`` (loaded by the one settings loader), as one ``FeatureSet``.

``site_features(configs)`` is what the ``rollups`` task, the read path (selections,
``FeatureView``), the selection catalogue and the feature catalogue use. It is built once per
config store (a bad formula fails here, naming the file, the feature and the position).
"""

from algotrade.config.site.settings import SiteDocuments, load_features
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.registry import GROUPS, SUPERSEDED

_BUILT: dict[int, tuple[SiteDocuments, FeatureSet]] = {}  # by store identity (kept alive)


def site_features(configs: SiteDocuments) -> FeatureSet:
    """Code groups + the site's expression features (built once per store)."""
    built = _BUILT.get(id(configs))
    if built is None or built[0] is not configs:
        built = (configs, FeatureSet.build(GROUPS, load_features(configs), SUPERSEDED))
        _BUILT[id(configs)] = built
    return built[1]
