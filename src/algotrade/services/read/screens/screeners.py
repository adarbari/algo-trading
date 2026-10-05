"""The screeners a user sees (``Screener``): every rule screen config, one per id, as it
resolves for the user (their own config, else the site preset it shares an id with; ADR 0015),
with whose runs are its (``owner``: the user's id, or ``site`` for a preset).

Configs, not results: a screener is listed whether or not it has run, and results stored for a
config that no longer exists (an archived screen) are not a screener. Only rule screens
(``impl = "rules"``): their runs are the shared ``results/rule_screen`` table the read model
serves (``runs.py``); a config that does not resolve is left out."""

from dataclasses import dataclass

from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.config.strategy.schema import RULES_IMPL
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.configs import config_ids, resolve_config
from algotrade.services.read.context import ReadContext

SCREENER = "screener"
SITE_SCOPE = "site"


@dataclass(frozen=True)
class Screener:
    """A rule screen as the user sees it. ``scope``: where its config lives (``site`` or the
    user's id); ``owner``: whose runs are its (the user's id, or ``site``); ``name``: the
    config's display name, else its id; ``version``: the config's current version."""

    id: str
    owner: str
    scope: str
    name: str
    version: int | None
    hash: str


def _screener(config: ResolvedConfig) -> Screener:
    owner = config.user.user_id
    return Screener(
        id=config.config.id,
        owner=owner,
        scope=SITE_SCOPE if owner == SITE_USER else owner,
        name=(config.config.name or "").strip() or config.config.id,
        version=config.screen_spec.version,
        hash=config.hash,
    )


def _owners(ctx: ReadContext) -> dict[str, str]:
    """``{config id: whose it is}``: the user's finalised configs, else the site presets."""
    user = ctx.user.user_id
    owners = dict.fromkeys(config_ids(ctx.configs, SITE_USER), SITE_USER)
    if user != SITE_USER:
        owners.update(dict.fromkeys(config_ids(ctx.configs, user), user))
    return owners


def _resolved(ctx: ReadContext, config_id: str, owner: str) -> Screener | None:
    try:  # resolved as its owner, as the run that stores its results resolves it
        config = resolve_config(ctx.configs, config_id, UserContext(owner))
    except ConfigurationError:
        return None
    if config.config.kind != SCREENER or config.config.impl != RULES_IMPL:
        return None
    return _screener(config)


def load_screener(ctx: ReadContext, config_id: str) -> Screener | None:
    """``config_id`` as the user sees it; ``None`` when it is not a rule screen the user sees
    (unknown, another kind, or a config that does not resolve)."""
    owner = _owners(ctx).get(config_id)
    return None if owner is None else _resolved(ctx, config_id, owner)


def load_screeners(ctx: ReadContext) -> tuple[Screener, ...]:
    """Every rule screen the user sees, one per id (sorted by id)."""
    found = (_resolved(ctx, i, owner) for i, owner in sorted(_owners(ctx).items()))
    return tuple(s for s in found if s is not None)
