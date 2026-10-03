"""Configuration: typed strategy/screener configs, selections and users (L3 site, L4 user),
typed site settings (``settings``) and the environment (``env``).

Parses and validates plain dicts (as loaded from TOML by ``storage``), resolves the layers
and hashes the result. No file I/O, except ``env``: the one reader of environment variables
and the local ``.env``.
"""

from algotrade.config.strategy.resolve import ResolvedConfig, resolve
from algotrade.config.strategy.schema import Group, Rule, Selection, StrategyConfig
from algotrade.config.user import UserContext

__all__ = [
    "Group",
    "ResolvedConfig",
    "Rule",
    "Selection",
    "StrategyConfig",
    "UserContext",
    "resolve",
]
