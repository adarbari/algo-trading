"""Typed config objects parsed from plain dicts (TOML). Errors name the offending path."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from algotrade.config.user import validate_id
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.predicates import (
    NO_VALUE_OPS,
    OPS,
    Group,
    Rule,
    RuleValue,
    Scalar,
)

__all__ = [
    "EVERY_INSTRUMENT",
    "KINDS",
    "NO_VALUE_OPS",
    "OPS",
    "RULES_IMPL",
    "RULE_SCREEN_KEYS",
    "Group",
    "Rule",
    "RuleValue",
    "Scalar",
    "Selection",
    "StrategyConfig",
    "parse_group",
    "parse_rule",
    "parse_selection",
    "parse_strategy",
]

KINDS = frozenset({"screener", "strategy"})
RULES_IMPL = "rules"
# The rule-screen part of a config (ADR 0029), kept raw here and parsed by
# ``config.strategy.screen_spec`` after the layers are merged. ``tiers`` and ``classify`` are
# legacy (ADR 0030): accepted so v1 / v2 presets parse, then ignored.
RULE_SCREEN_KEYS = frozenset(
    {"version", "criteria", "tiers", "flags", "classify", "columns", "rank"}
)


@dataclass(frozen=True)
class Selection:
    name: str
    where: Group
    max_instruments: int | None = None
    order_by: str | None = None  # field; descending when max_instruments is set

    def narrowed(self, extra: Group) -> "Selection":
        """This selection AND ``extra`` (how a user narrows a shared preset)."""
        return Selection(
            self.name, Group("all", (self.where, extra)), self.max_instruments, self.order_by
        )


# A rule screen names no selection (ADR 0030): it runs over every instrument of the snapshot and
# its first criteria say who is screened.
EVERY_INSTRUMENT = Selection("all", Group("all", ()))


@dataclass(frozen=True)
class StrategyConfig:
    id: str
    kind: str
    impl: str
    params: Mapping[str, Scalar] = field(default_factory=dict)
    selection: str | Selection | None = None
    selection_overrides: Group | None = None
    exports: tuple[str, ...] = ()
    settings: Mapping[str, Any] = field(default_factory=dict)  # [screening] / [backtest] / [regime]
    rules: Mapping[str, Any] = field(default_factory=dict)  # RULE_SCREEN_KEYS, impl "rules" only
    name: str | None = None  # display name for pages (not part of the hash); the id when None


def _fail(path: str, message: str) -> ConfigurationError:
    return ConfigurationError(f"{path}: {message}")


def _scalar(value: Any, path: str) -> Scalar:
    if isinstance(value, (str, int, float, bool)):
        return value
    raise _fail(path, f"expected a string, number or boolean, got {type(value).__name__}")


def parse_rule(raw: Mapping[str, Any], path: str) -> Rule:
    unknown = set(raw) - {"field", "op", "value"}
    if unknown:
        raise _fail(path, f"unknown keys {sorted(unknown)}")
    if not isinstance(raw.get("field"), str):
        raise _fail(path, "rule needs a string 'field'")
    op = raw.get("op")
    if op not in OPS:
        raise _fail(path, f"op must be one of {sorted(OPS)}, got {op!r}")
    if op in NO_VALUE_OPS:
        return Rule(raw["field"], op)
    if "value" not in raw:
        raise _fail(path, f"op {op!r} needs a 'value'")
    value = raw["value"]
    if op in ("in", "not_in", "between"):
        if not isinstance(value, list) or not value:
            raise _fail(path, f"op {op!r} needs a non-empty list")
        if op == "between" and len(value) != 2:
            raise _fail(path, "between needs [low, high]")
        return Rule(raw["field"], op, tuple(_scalar(v, f"{path}.value") for v in value))
    return Rule(raw["field"], op, _scalar(value, f"{path}.value"))


def parse_group(raw: Mapping[str, Any], path: str) -> Group:
    keys = [k for k in ("all", "any", "not") if k in raw]
    if len(keys) != 1 or len(raw) != 1:
        raise _fail(path, "a group has exactly one of 'all', 'any' or 'not'")
    kind = keys[0]
    items = raw[kind] if kind != "not" else [raw[kind]]
    if not isinstance(items, list) or not items:
        raise _fail(f"{path}.{kind}", "expected a non-empty list")
    children: list[Rule | Group] = []
    for i, item in enumerate(items):
        child_path = f"{path}.{kind}[{i}]" if kind != "not" else f"{path}.not"
        if not isinstance(item, Mapping):
            raise _fail(child_path, "expected a table")
        is_group = any(k in item for k in ("all", "any", "not"))
        children.append(parse_group(item, child_path) if is_group else parse_rule(item, child_path))
    return Group(kind, tuple(children))


def parse_selection(raw: Mapping[str, Any], path: str) -> Selection:
    unknown = set(raw) - {"name", "where", "max_instruments", "order_by"}
    if unknown:
        raise _fail(path, f"unknown keys {sorted(unknown)}")
    name = validate_id("selection", str(raw.get("name", "")))
    if not isinstance(raw.get("where"), Mapping):
        raise _fail(path, "selection needs a 'where' group")
    limit = raw.get("max_instruments")
    if limit is not None and (not isinstance(limit, int) or limit <= 0):
        raise _fail(f"{path}.max_instruments", "must be a positive integer")
    order_by = raw.get("order_by")
    if limit is not None and not isinstance(order_by, str):
        raise _fail(path, "max_instruments needs an 'order_by' field")
    return Selection(name, parse_group(raw["where"], f"{path}.where"), limit, order_by)


def parse_strategy(raw: Mapping[str, Any], path: str) -> StrategyConfig:
    allowed = {
        "id",
        "kind",
        "impl",
        "params",
        "selection",
        "selection_overrides",
        "schedule",  # legacy (ADR 0033): every finalised screener runs nightly; ignored
        "exports",
        "screening",
        "backtest",
        "regime",
        "extends",
        "name",
        *RULE_SCREEN_KEYS,
    }
    unknown = set(raw) - allowed
    if unknown:
        raise _fail(path, f"unknown keys {sorted(unknown)}")
    cid = validate_id("config", str(raw.get("id", "")))
    name = raw.get("name")
    if name is not None and (not isinstance(name, str) or not name.strip()):
        raise _fail(f"{path}.name", "expected a non-empty display name")
    if raw.get("kind") not in KINDS:
        raise _fail(f"{path}.kind", f"must be one of {sorted(KINDS)}")
    if not isinstance(raw.get("impl"), str):
        raise _fail(f"{path}.impl", "required: the registered strategy/screener name")
    params = raw.get("params", {})
    if not isinstance(params, Mapping):
        raise _fail(f"{path}.params", "expected a table")
    selection_raw = raw.get("selection")
    selection: str | Selection | None
    if isinstance(selection_raw, str) or selection_raw is None:
        selection = selection_raw
    elif isinstance(selection_raw, Mapping):
        selection = parse_selection(selection_raw, f"{path}.selection")
    else:
        raise _fail(f"{path}.selection", "expected a preset name or a selection table")
    overrides = raw.get("selection_overrides")
    exports = raw.get("exports", [])
    if not isinstance(exports, list) or not all(isinstance(e, str) for e in exports):
        raise _fail(f"{path}.exports", "expected a list of export names")
    settings = {k: raw[k] for k in ("screening", "backtest", "regime") if k in raw}
    rules = {k: raw[k] for k in sorted(RULE_SCREEN_KEYS) if k in raw}
    if raw["impl"] == RULES_IMPL and "criteria" not in rules:
        raise _fail(path, "a rule screen (impl = 'rules') needs [criteria]")
    if rules and raw["impl"] != RULES_IMPL:
        raise _fail(path, f"{sorted(rules)} belong to rule screens (impl = 'rules') only")
    return StrategyConfig(
        id=cid,
        kind=raw["kind"],
        impl=raw["impl"],
        params={k: _scalar(v, f"{path}.params.{k}") for k, v in params.items()},
        selection=selection,
        selection_overrides=parse_group(overrides, f"{path}.selection_overrides")
        if overrides
        else None,
        exports=tuple(exports),
        settings=settings,
        rules=rules,
        name=name,
    )
