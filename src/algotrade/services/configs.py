"""Use case: resolve configs from the ``ConfigStore`` and find scheduled ones."""

from collections.abc import Mapping
from typing import Any

from algotrade.config.catalog import FieldCatalog
from algotrade.config.env import user_id
from algotrade.config.resolve import ResolvedConfig, resolve
from algotrade.config.user import SITE_USER, UserContext
from algotrade.features.registry import FEATURES
from algotrade.storage.config_store import ConfigStore


def default_user(fallback: str) -> UserContext:
    """``$ALGOTRADE_USER`` if set, else ``fallback`` (CLIs: ``local``; site screens: ``site``)."""
    return UserContext(user_id(fallback))


def field_catalog() -> FieldCatalog:
    """Every field a selection may reference: L1 instrument columns + registered rollups."""
    return FieldCatalog.build({spec.key: spec.columns for spec in FEATURES.values()})


def resolve_config(
    store: ConfigStore,
    config_id: str,
    user: UserContext,
    overrides: Mapping[str, Any] | None = None,
) -> ResolvedConfig:
    return resolve(config_id, user, store.load, overrides, field_catalog())


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
