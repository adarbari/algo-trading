"""Configuration: typed strategy/screener configs, selections and users (L3 site, L4 user).

Pure: parses and validates plain dicts (as loaded from TOML by ``storage``), resolves the
layers and hashes the result. No I/O here.
"""

from algotrade.config.resolve import ResolvedConfig, resolve
from algotrade.config.schema import Group, Rule, Selection, StrategyConfig
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
