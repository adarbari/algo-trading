"""Resolve a config through its layers and fingerprint the result.

Order (later wins): built-in defaults < L3 site (defaults, preset) < L4 user < run overrides.
A user config either *narrows* a preset (``selection_overrides``: AND-ed with the preset's
rules, so preset improvements still apply) or *replaces* it (its own ``selection``).

``ResolvedConfig.features``: the user expression features the selection references (with the
user features those read), so editing one changes the hash (``with_features``; ADR 0023
step 4). Site features are versioned instead: a changed site formula bumps its version.
"""

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from algotrade.config.site.fields import reject_secrets
from algotrade.config.site.settings import (
    BacktestSettings,
    FeatureDefinition,
    ScreeningSettings,
    site_defaults,
)
from algotrade.config.strategy.catalog import FieldCatalog
from algotrade.config.strategy.schema import (
    Group,
    Rule,
    Selection,
    StrategyConfig,
    parse_selection,
    parse_strategy,
)
from algotrade.config.strategy.screen_spec import check_screen_spec, screen_spec
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.screen_spec import ScreenSpec

# (scope, kind, name) -> document; scope is "site" or a user id;
# kind is "defaults", "strategies" or "selections".
type DocumentLoader = Callable[[str, str, str], Mapping[str, Any] | None]

BUILTIN_DEFAULTS: Mapping[str, Any] = {
    "screening": {"min_coverage": 0.98, "max_universe_age_days": 45},
    "backtest": {
        "initial_cash": 100_000.0,
        "cash_buffer": 0.01,
        "lot_size": 1.0,
        "periods_per_year": 252,
        "price_adjustment": "splits",
        "costs": {"commission_bps": 1.0, "min_commission": 0.0, "slippage_bps": 5.0},
        "limits": {"max_position_weight": 1.0, "max_gross_exposure": 1.0, "allow_short": False},
    },
}


def _checked(load: DocumentLoader) -> DocumentLoader:
    def wrapped(scope: str, kind: str, name: str) -> Mapping[str, Any] | None:
        document = load(scope, kind, name)
        if document is not None:
            reject_secrets(document, f"{scope}/{kind}/{name}")
        return document

    return wrapped


def deep_merge(base: Mapping[str, Any], over: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def group_to_dict(group: Group) -> dict[str, Any]:
    items = [group_to_dict(c) if isinstance(c, Group) else rule_to_dict(c) for c in group.children]
    return {group.kind: items[0] if group.kind == "not" else items}


def rule_to_dict(rule: Rule) -> dict[str, Any]:
    out: dict[str, Any] = {"field": rule.field, "op": rule.op}
    if rule.value is not None:
        out["value"] = list(rule.value) if isinstance(rule.value, tuple) else rule.value
    return out


def selection_to_dict(selection: Selection) -> dict[str, Any]:
    out: dict[str, Any] = {"name": selection.name, "where": group_to_dict(selection.where)}
    if selection.max_instruments is not None:
        out.update(max_instruments=selection.max_instruments, order_by=selection.order_by)
    return out


@dataclass(frozen=True)
class ResolvedConfig:
    config: StrategyConfig
    selection: Selection | None
    settings: Mapping[str, Any]
    user: UserContext
    layers: tuple[str, ...] = ()
    hash: str = field(default="")
    features: tuple[FeatureDefinition, ...] = ()  # referenced user features, dependency order

    @property
    def screening(self) -> ScreeningSettings:
        """The resolved ``[screening]`` settings, typed (validated by ``resolve``)."""
        return ScreeningSettings.parse(
            self.settings.get("screening"), f"{self.config.id} [screening]"
        )

    @property
    def backtest(self) -> BacktestSettings:
        """The resolved ``[backtest]`` settings, typed (validated by ``resolve``)."""
        return BacktestSettings.parse(self.settings.get("backtest"), f"{self.config.id} [backtest]")

    @property
    def screen_spec(self) -> ScreenSpec:
        """The rule-screen spec (``impl = "rules"`` only; validated by ``resolve``)."""
        return screen_spec(self.config)

    def canonical(self) -> dict[str, Any]:
        """Everything that affects results (not provenance), in a stable JSON shape."""
        c = self.config
        return (
            {
                "id": c.id,
                "kind": c.kind,
                "impl": c.impl,
                "params": dict(sorted(c.params.items())),
                "selection": selection_to_dict(self.selection) if self.selection else None,
                "schedule": c.schedule,
                "exports": list(c.exports),
                "settings": self.settings,
            }
            | ({"rules": c.rules} if c.rules else {})
            | (
                {"features": {d.name: d.canonical() for d in self.features}}
                if self.features
                else {}
            )
        )

    def with_features(self, features: tuple[FeatureDefinition, ...]) -> "ResolvedConfig":
        """This config reading these user features (they join the hash)."""
        out = replace(self, features=features)
        return replace(out, hash=fingerprint(out.canonical()))


def fingerprint(payload: Mapping[str, Any]) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def _strategy_document(
    config_id: str, user: UserContext, load: DocumentLoader
) -> tuple[dict[str, Any], list[str]]:
    user_doc = load(user.user_id, "strategies", config_id) if user.user_id != SITE_USER else None
    base_id = str(user_doc.get("extends", config_id)) if user_doc else config_id
    site_doc = load("site", "strategies", base_id)
    if user_doc and "extends" in user_doc and site_doc is None:
        raise ConfigurationError(f"{user.user_id}/{config_id}: extends unknown preset {base_id!r}")
    if user_doc is None and site_doc is None:
        raise ConfigurationError(f"unknown config {config_id!r} for user {user.user_id!r}")
    layers = [f"site/strategies/{base_id}"] if site_doc else []
    merged = dict(site_doc or {})
    if user_doc:
        merged = deep_merge(merged, {k: v for k, v in user_doc.items() if k != "extends"})
        merged["id"] = config_id
        layers.append(f"{user.user_id}/strategies/{config_id}")
    return merged, layers


def _selection(
    ref: str | Selection | None, user: UserContext, load: DocumentLoader, layers: list[str]
) -> Selection | None:
    if ref is None or isinstance(ref, Selection):
        return ref
    for scope in (user.user_id, "site"):
        doc = load(scope, "selections", ref)
        if doc is not None:
            layers.append(f"{scope}/selections/{ref}")
            return parse_selection(doc, f"{scope}/selections/{ref}")
    raise ConfigurationError(f"unknown selection {ref!r}")


def resolve(
    config_id: str,
    user: UserContext,
    load: DocumentLoader,
    overrides: Mapping[str, Any] | None = None,
    catalog: FieldCatalog | None = None,
) -> ResolvedConfig:
    load = _checked(load)
    if overrides:
        reject_secrets(overrides, "run-overrides")
    document, layers = _strategy_document(config_id, user, load)
    if overrides:
        document = deep_merge(document, overrides)
        layers.append("run-overrides")
    config = parse_strategy(document, "/".join(layers[-1:]) or config_id)
    selection = _selection(config.selection, user, load, layers)
    if config.selection_overrides is not None:
        if selection is None:
            raise ConfigurationError(f"{config_id}: selection_overrides need a base selection")
        selection = selection.narrowed(config.selection_overrides)
    if catalog is not None and selection is not None:
        catalog.check(selection.where, f"{config_id}.selection")
        if selection.order_by:
            catalog.check_field(selection.order_by, f"{config_id}.selection.order_by")
    if config.rules:
        spec = screen_spec(config)  # a malformed rule screen fails here, with its path
        if catalog is not None:
            check_screen_spec(spec, catalog, config_id)
    defaults = deep_merge(BUILTIN_DEFAULTS, site_defaults(load))
    settings = deep_merge(defaults, config.settings)
    resolved = ResolvedConfig(config, selection, settings, user, tuple(layers))
    _ = resolved.screening, resolved.backtest  # typed: a bad value fails here, with its path
    return ResolvedConfig(
        config, selection, settings, user, tuple(layers), fingerprint(resolved.canonical())
    )
