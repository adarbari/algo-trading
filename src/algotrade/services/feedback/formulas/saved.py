"""The trader's own saved expression features, as ``accepted_payload`` takes them: the catalogue
of the user (``features.site.user_features``, the one owner) without the site's. Reads only."""

from algotrade.config.site.features.definitions import FeatureDefinition
from algotrade.config.site.settings import SiteDocuments
from algotrade.features.site import user_features


def saved_features(configs: SiteDocuments, user: str) -> list[FeatureDefinition]:
    """``user``'s own expression features (never a site one)."""
    found = user_features(configs, user).expressions.values()
    return [e.definition for e in found if e.scope != "site"]
