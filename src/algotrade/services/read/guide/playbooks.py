"""The site playbooks the Guide reads (ADR 0051): one per site rule-screen preset
(``config/site/presets/screeners/<id>/``, its latest version through the config store), with
resolved as the ``site`` user exactly as the nightly runs it (``services.configs``), with its
name, its family from ``config/site/guide/sections.toml`` and its ``ScreenSpec``; in Guide
order (the families' order, then any preset no family lists, by id). A preset that does not
resolve as a rule screen is left out (the screener read and the nightly report it).

Also each criterion's rule as text, ``op value mode tolerance`` in the rule grammar's own
words (``docs/screeners/rules.md``): ``gte 50000000 soft tolerance relative 0.2``."""

from dataclasses import dataclass

from algotrade.config.site.guide.sections import load_guide_sections
from algotrade.config.strategy.schema import RULES_IMPL
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.predicates import NO_VALUE_OPS
from algotrade.core.model.screen_spec import Criterion, ScreenSpec
from algotrade.services.configs import resolve_config
from algotrade.services.read.context import Stores
from algotrade.services.read.screens.screeners import SCREENER
from algotrade.storage.configs.files import SCREENERS


@dataclass(frozen=True)
class SitePlaybook:
    """A site preset as the Guide reads it: ``family`` (a ``sections.toml`` family id;
    ``None``: no family lists it) and its ``spec``."""

    id: str
    name: str
    family: str | None
    spec: ScreenSpec


def site_playbooks(ctx: Stores) -> tuple[SitePlaybook, ...]:
    """Every site rule-screen preset, in Guide order (module docstring)."""
    families = load_guide_sections(ctx.configs).families
    family_of = {p: f.id for f in families for p in f.presets}
    listed = [p for f in families for p in f.presets]
    stored = ctx.configs.names(SITE_USER, SCREENERS)
    ordered = [p for p in listed if p in stored] + sorted(p for p in stored if p not in family_of)
    found = (_playbook(ctx, preset, family_of.get(preset)) for preset in ordered)
    return tuple(p for p in found if p is not None)


def _playbook(ctx: Stores, preset: str, family: str | None) -> SitePlaybook | None:
    try:  # as the nightly resolves it (services.configs.nightly_screeners)
        resolved = resolve_config(ctx.configs, preset, UserContext(SITE_USER))
    except ConfigurationError:
        return None
    config = resolved.config
    if config.kind != SCREENER or config.impl != RULES_IMPL:
        return None
    name = (config.name or "").strip() or preset
    return SitePlaybook(preset, name, family, resolved.screen_spec)


def rule_text(criterion: Criterion) -> str:
    """``criterion``'s rule in the grammar's words: ``op [value] mode [tolerance [relative] n]``."""
    rule = criterion.rule
    words = [rule.op]
    if rule.op not in NO_VALUE_OPS:
        words.append(_value(rule.value))
    words.append(criterion.mode.value)
    tolerance = criterion.tolerance
    if tolerance is not None:
        words += [
            "tolerance",
            *(["relative"] if tolerance.relative else []),
            _value(tolerance.amount),
        ]
    return " ".join(words)


def _value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, tuple | list):
        return "[" + ", ".join(_value(v) for v in value) + "]"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
