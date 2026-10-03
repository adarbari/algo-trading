"""Strategy and screener configs for display: every config a user sees (site presets and the
user's own) and one config resolved through its layers, with its hash (ADR 0015)."""

from dataclasses import dataclass
from typing import Any

from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.configs import resolve_config
from algotrade.services.explore.store import NotFoundError, ReadStore

KIND = "strategies"  # config documents of both kinds (strategy, screener) live here


@dataclass(frozen=True)
class ConfigSummary:
    config_id: str
    scope: str  # "site" (a preset) or the user's id
    kind: str | None  # strategy | screener (None when it does not resolve)
    impl: str | None
    schedule: str | None
    selection: str | None  # the named selection, or "inline"
    hash: str | None
    error: str | None  # why the config does not resolve


def _owner(scope: str) -> UserContext:
    return UserContext(SITE_USER if scope == "site" else scope)


def _summary(store: ReadStore, config_id: str, scope: str) -> ConfigSummary:
    try:
        resolved = resolve_config(store.configs, config_id, _owner(scope))
    except ConfigurationError as exc:
        return ConfigSummary(config_id, scope, None, None, None, None, None, str(exc))
    c = resolved.config
    selection = c.selection if isinstance(c.selection, str) or c.selection is None else "inline"
    return ConfigSummary(
        config_id, scope, c.kind, c.impl, c.schedule, selection, resolved.hash, None
    )


def config_list(store: ReadStore, kind: str | None = None) -> list[ConfigSummary]:
    """Site presets, then the user's own configs (``kind``: only strategies or screeners)."""
    scopes = ["site", *([store.user.user_id] if store.user.user_id != SITE_USER else [])]
    out = [_summary(store, n, s) for s in scopes for n in store.configs.names(s, KIND)]
    return [c for c in out if kind is None or c.kind == kind]


def resolved(store: ReadStore, config_id: str) -> ResolvedConfig:
    """``config_id`` resolved for the store's user (their own config, else the preset)."""
    try:
        return resolve_config(store.configs, config_id, store.user)
    except ConfigurationError as exc:
        if "unknown config" in str(exc):
            raise NotFoundError(str(exc)) from exc
        raise


@dataclass(frozen=True)
class ConfigDetail:
    config_id: str
    user: str
    hash: str
    layers: list[str]
    resolved: dict[str, Any]  # kind, impl, params, selection, schedule, exports, settings


def config_detail(store: ReadStore, config_id: str) -> ConfigDetail:
    config = resolved(store, config_id)
    return ConfigDetail(
        config_id, config.user.user_id, config.hash, list(config.layers), config.canonical()
    )
