"""The strategy and screener configs a user sees (``Config``): the site presets, then the
user's own, each resolved through its layers with its hash (ADR 0015), or why it does not
resolve. Backtests run the strategy configs; the Screeners page lists the screener ones.

Configs are not session data: the list is the same for every session (the configs as they are
now)."""

from dataclasses import dataclass

from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.configs import config_ids, resolve_config
from algotrade.services.read.context import NotFoundError, Stores
from algotrade.storage.configs.store import ConfigStore

SITE_SCOPE = "site"


@dataclass(frozen=True)
class Config:
    """One config as its scope has it. ``scope``: ``site`` (a preset) or the user's id;
    ``kind``: ``strategy`` or ``screener`` (None when it does not resolve); ``selection``: the
    named selection, or ``inline``; ``error``: why it does not resolve (None: it does)."""

    config_id: str
    scope: str
    kind: str | None
    impl: str | None
    selection: str | None
    hash: str | None
    error: str | None


def _owner(scope: str) -> UserContext:
    return UserContext(SITE_USER if scope == SITE_SCOPE else scope)


def _config(configs: ConfigStore, config_id: str, scope: str) -> Config:
    try:
        resolved = resolve_config(configs, config_id, _owner(scope))
    except ConfigurationError as exc:
        return Config(config_id, scope, None, None, None, None, str(exc))
    c = resolved.config
    selection = c.selection if isinstance(c.selection, str) or c.selection is None else "inline"
    return Config(config_id, scope, c.kind, c.impl, selection, resolved.hash, None)


def configs_of(configs: ConfigStore, user: UserContext, kind: str | None = None) -> list[Config]:
    """Site presets, then ``user``'s own configs (``kind``: only strategies or screeners)."""
    scopes = [SITE_SCOPE, *([user.user_id] if user.user_id != SITE_USER else [])]
    found = [_config(configs, n, s) for s in scopes for n in config_ids(configs, s)]
    return [c for c in found if kind is None or c.kind == kind]


def resolved_for(configs: ConfigStore, user: UserContext, config_id: str) -> ResolvedConfig:
    """``config_id`` resolved for ``user`` (their own config, else the preset);
    ``NotFoundError`` when there is no such config."""
    try:
        return resolve_config(configs, config_id, user)
    except ConfigurationError as exc:
        if "unknown config" in str(exc):
            raise NotFoundError(str(exc)) from exc
        raise


def load_configs(ctx: Stores, kind: str | None = None) -> tuple[Config, ...]:
    """Every config ``ctx.user`` sees (``kind``: only ``strategy`` or ``screener``)."""
    return tuple(configs_of(ctx.configs, ctx.user, kind))
