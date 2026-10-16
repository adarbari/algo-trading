"""The screeners a user sees (``Screener``): every rule screen config, one per id, as it
resolves for the user (their own config, else the site preset it shares an id with; ADR 0015),
with whose runs are its (``owner``: the user's id, or ``site`` for a preset).

Configs, not results: a screener is listed whether or not it has run, and results stored for a
config that no longer exists (an archived screen) are not a screener. Only rule screens
(``impl = "rules"``): their runs are the shared ``results/rule_screen`` table the read model
serves (``runs.py``); a config that does not resolve is left out."""

from dataclasses import dataclass

from algotrade.config.strategy.regime import REGIME_LABELS
from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.config.strategy.schema import RULE_IMPLS
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.predicates import RuleValue
from algotrade.services.configs import config_ids, resolve_config
from algotrade.services.read.context import ReadContext, catalogue_key

SCREENER = "screener"
SITE_SCOPE = "site"


@dataclass(frozen=True)
class ScreenCriterion:
    """One criterion of the screen, in spec (funnel) order: the catalogue field it judges, its
    mode (``hard``, ``soft``, ``score``) and its rule as the config states it: the operator
    ``op`` and the threshold ``value`` (a scalar, a tuple for ``in`` / ``between``; ``None``
    for an operator without one), in the field's stored unit."""

    id: str
    field: str
    mode: str
    op: str
    value: RuleValue = None


@dataclass(frozen=True)
class ScreenColumn:
    """One of the screen's display columns (``[columns]``): its name and the catalogue field
    the run stored for it."""

    name: str
    field: str


@dataclass(frozen=True)
class Screener:
    """A rule screen as the user sees it. ``scope``: where its config lives (``site`` or the
    user's id); ``owner``: whose runs are its (the user's id, or ``site``); ``name``: the
    config's display name, else its id; ``version``: the config's current version;
    ``criteria`` and ``display_columns``: the current config's, in spec order;
    ``regime_enabled`` / ``pause_in``: its resolved ``[regime]`` gate (ADR 0049): whether it is
    on for this screener and the labels, calmest first, in which its picks are PAUSED."""

    id: str
    owner: str
    scope: str
    name: str
    version: int | None
    hash: str
    criteria: tuple[ScreenCriterion, ...]
    display_columns: tuple[ScreenColumn, ...]
    regime_enabled: bool = False
    pause_in: tuple[str, ...] = ()


def _screener(config: ResolvedConfig) -> Screener:
    owner = config.user.user_id
    spec = config.screen_spec
    regime = config.regime
    return Screener(
        id=config.config.id,
        owner=owner,
        scope=SITE_SCOPE if owner == SITE_USER else owner,
        name=(config.config.name or "").strip() or config.config.id,
        version=spec.version,
        hash=config.hash,
        criteria=tuple(
            ScreenCriterion(c.id, c.field, c.mode.value, c.rule.op, c.rule.value)
            for c in spec.criteria
        ),
        display_columns=tuple(ScreenColumn(n, f) for n, f in spec.columns),
        regime_enabled=regime.enabled,
        pause_in=tuple(label for label in REGIME_LABELS if label in config.gate_pauses),
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
    if config.config.kind != SCREENER or config.config.impl not in RULE_IMPLS:
        return None
    return _screener(config)


def _stamp(ctx: ReadContext) -> tuple[object, ...]:
    """What the resolved screeners depend on, cheaply: the screens and finalised versions each
    scope holds (a version file is immutable, a new one is a save), and the user's catalogue
    (their features join a screen's hash). Site files change only with a deploy, which restarts
    the API."""
    scopes = (SITE_USER,) if ctx.user.user_id == SITE_USER else (SITE_USER, ctx.user.user_id)
    held = tuple(
        (scope, name, tuple(ctx.configs.versions(scope, name)))
        for scope in scopes
        for name in sorted(config_ids(ctx.configs, scope))
    )
    return (ctx.user.user_id, held, catalogue_key(ctx))


def load_screener(ctx: ReadContext, config_id: str) -> Screener | None:
    """``config_id`` as the user sees it; ``None`` when it is not a rule screen the user sees
    (unknown, another kind, or a config that does not resolve)."""
    return next((s for s in load_screeners(ctx) if s.id == config_id), None)


def load_screeners(ctx: ReadContext) -> tuple[Screener, ...]:
    """Every rule screen the user sees, one per id (sorted by id). Resolving a config reads its
    TOML layers and rebuilds the catalogue, so the answer is shared across requests (one page
    load asks for it from the regime strip, the status strip and the ideas table) and keyed on
    ``_stamp``: a saved version or an edited user feature is a new key."""

    def compute() -> tuple[Screener, ...]:
        found = (_resolved(ctx, i, owner) for i, owner in sorted(_owners(ctx).items()))
        return tuple(s for s in found if s is not None)

    return ctx.cache.get_or_compute(("screeners", _stamp(ctx)), compute)  # type: ignore[no-any-return]
