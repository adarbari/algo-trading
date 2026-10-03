"""Use case: resolve configs from the ``ConfigStore`` and find scheduled ones."""

from collections.abc import Mapping
from typing import Any

from algotrade.config.env import user_id
from algotrade.config.strategy.catalog import FieldCatalog
from algotrade.config.strategy.resolve import ResolvedConfig, resolve
from algotrade.config.user import SITE_USER, UserContext
from algotrade.features.registry import catalogue_columns
from algotrade.services.features import site_features
from algotrade.storage.configs.store import ConfigStore


def default_user(fallback: str) -> UserContext:
    """``$ALGOTRADE_USER`` if set, else ``fallback`` (CLIs: ``local``; site screens: ``site``)."""
    return UserContext(user_id(fallback))


def field_catalog(store: ConfigStore | None = None) -> FieldCatalog:
    """Every field a selection may reference: L1 instrument columns, registered rollups and
    the site's expression features (``store``'s, default: the site config directory)."""
    fs = site_features(store)
    expressions = {n: e.feature.dtype for n, e in fs.expressions.items()}
    return FieldCatalog.build(catalogue_columns(), expressions, fs.moved_field)


def resolve_config(
    store: ConfigStore,
    config_id: str,
    user: UserContext,
    overrides: Mapping[str, Any] | None = None,
) -> ResolvedConfig:
    return resolve(config_id, user, store.load, overrides, field_catalog(_features_store(store)))


def _features_store(store: ConfigStore) -> ConfigStore | None:
    """``store`` when it declares expression features, else the site default (a store that
    holds only strategy configs, e.g. in tests, still sees the site's features)."""
    return store if store.names("site", "features") else None


def scheduled(store: ConfigStore, schedule: str = "nightly") -> list[ResolvedConfig]:
    """Configs to run on ``schedule``: site presets (as the ``site`` user) and each user's own."""
    runs: list[ResolvedConfig] = []
    owners = [SITE_USER, *store.users()]
    for owner in owners:
        scope = "site" if owner == SITE_USER else owner
        for config_id in store.names(scope, "strategies"):
            resolved = resolve_config(store, config_id, UserContext(owner))
            if resolved.config.schedule == schedule:
                runs.append(resolved)
    return runs
