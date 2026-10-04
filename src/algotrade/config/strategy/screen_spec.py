"""Parse and validate a rule screen (ADR 0029, ``docs/screeners/rules.md``) into a
``ScreenSpec``. Fails closed: every problem is a ``ConfigurationError`` naming its path, so
an invalid spec never runs or finalises.

Structural checks live in ``parse_screen_spec``; ``check_screen_spec`` checks the fields
against the catalogue (they exist, the values fit their types).
"""

import re
from collections.abc import Mapping
from typing import Any

from algotrade.config.strategy.catalog import FieldCatalog
from algotrade.config.strategy.schema import RULES_IMPL, StrategyConfig, parse_group, parse_rule
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id
from algotrade.core.model.predicates import NUMERIC_OPS, Group, Rule
from algotrade.core.model.screen_spec import (
    NEAR_MISS_DECISIONS,
    Criterion,
    Mode,
    ScreenSpec,
    Tolerance,
)

_CRITERION_KEYS = frozenset(
    {"field", "op", "value", "mode", "tolerance", "on_miss", "label", "enabled"}
)
_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_NUMERIC_TYPES = frozenset({"float", "float32", "int"})


def _fail(path: str, message: str) -> ConfigurationError:
    return ConfigurationError(f"{path}: {message}")


def _table(raw: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise _fail(path, "expected a table")
    return raw


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _thresholds(rule: Rule) -> tuple[Any, ...]:
    return rule.value if isinstance(rule.value, tuple) else (rule.value,)


def _tolerance(raw: Any, rule: Rule, path: str) -> Tolerance:
    if rule.op not in NUMERIC_OPS:
        raise _fail(path, f"a tolerance needs a numeric comparison {sorted(NUMERIC_OPS)}")
    if not all(_number(v) for v in _thresholds(rule)):
        raise _fail(path, "a tolerance needs numeric thresholds")
    if _number(raw):
        tolerance = Tolerance(float(raw))
    elif isinstance(raw, Mapping) and set(raw) == {"relative"} and _number(raw["relative"]):
        tolerance = Tolerance(float(raw["relative"]), relative=True)
        if any(v == 0 for v in _thresholds(rule)):
            raise _fail(path, "a relative tolerance needs a non-zero threshold")
    else:
        raise _fail(path, "expected a number (absolute) or { relative = r }")
    if not tolerance.amount > 0:
        raise _fail(path, "must be greater than 0")
    return tolerance


def parse_criterion(cid: str, raw: Mapping[str, Any], path: str) -> Criterion | None:
    """``None`` when ``enabled = false`` (also how a user drops an inherited criterion)."""
    unknown = set(raw) - _CRITERION_KEYS
    if unknown:
        raise _fail(path, f"unknown keys {sorted(unknown)}")
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise _fail(f"{path}.enabled", "expected true or false")
    if not enabled:
        return None
    validate_id("criterion", cid)
    rule = parse_rule({k: raw[k] for k in ("field", "op", "value") if k in raw}, path)
    try:
        mode = Mode(raw.get("mode", Mode.HARD.value))
    except ValueError:
        raise _fail(f"{path}.mode", f"must be one of {[m.value for m in Mode]}") from None
    tolerance = None
    if "tolerance" in raw:
        if mode is Mode.HARD:
            raise _fail(f"{path}.tolerance", "a hard criterion is strict: no tolerance")
        tolerance = _tolerance(raw["tolerance"], rule, f"{path}.tolerance")
    elif mode is Mode.SOFT:
        raise _fail(path, "a soft criterion needs a tolerance (its near-miss band)")
    on_miss = raw.get("on_miss", "WATCH")
    if "on_miss" in raw and mode is not Mode.SOFT:
        raise _fail(f"{path}.on_miss", "only a soft criterion has a near-miss decision")
    if on_miss not in NEAR_MISS_DECISIONS:
        raise _fail(f"{path}.on_miss", f"must be one of {list(NEAR_MISS_DECISIONS)}")
    label = raw.get("label")
    if label is not None and not isinstance(label, str):
        raise _fail(f"{path}.label", "expected a string")
    return Criterion(cid, rule, mode, tolerance, on_miss, label)


def _groups(raw: Any, path: str) -> tuple[tuple[str, Group], ...]:
    out = []
    for name, group in _table(raw, path).items():
        if not _NAME.match(name):
            raise _fail(f"{path}.{name}", "use 1-64 of [A-Za-z0-9_-]")
        out.append((name, parse_group(_table(group, f"{path}.{name}"), f"{path}.{name}")))
    return tuple(out)


def _field(raw: Any, path: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise _fail(path, "expected a field name")
    return raw


def _rank(raw: Any, path: str) -> tuple[str | None, bool]:
    table = _table(raw, path)
    unknown = set(table) - {"tie_break", "tie_break_order"}
    if unknown:
        raise _fail(path, f"unknown keys {sorted(unknown)}")
    order = table.get("tie_break_order", "desc")
    if order not in ("asc", "desc"):
        raise _fail(f"{path}.tie_break_order", "must be 'asc' or 'desc'")
    tie_break = _field(table["tie_break"], f"{path}.tie_break") if "tie_break" in table else None
    return tie_break, order == "desc"


def parse_screen_spec(config_id: str, raw: Mapping[str, Any], path: str) -> ScreenSpec:
    """``raw``: the rule-screen keys of a merged config (``StrategyConfig.rules``)."""
    criteria_raw = _table(raw.get("criteria"), f"{path}.criteria")
    parsed = (
        parse_criterion(cid, _table(c, f"{path}.criteria.{cid}"), f"{path}.criteria.{cid}")
        for cid, c in criteria_raw.items()
    )
    criteria = tuple(c for c in parsed if c is not None)
    if not criteria:
        raise _fail(f"{path}.criteria", "needs at least one enabled criterion")
    version = raw.get("version")
    if version is not None and (not isinstance(version, int) or isinstance(version, bool)):
        raise _fail(f"{path}.version", "expected a positive integer")
    if version is not None and version < 1:
        raise _fail(f"{path}.version", "expected a positive integer")
    columns = tuple(
        (name, _field(f, f"{path}.columns.{name}"))
        for name, f in _table(raw.get("columns", {}), f"{path}.columns").items()
    )
    classify = raw.get("classify")
    tie_break, descending = _rank(raw.get("rank", {}), f"{path}.rank")
    return ScreenSpec(
        id=config_id,
        criteria=criteria,
        version=version,
        tiers=_groups(raw.get("tiers", {}), f"{path}.tiers"),
        flags=_groups(raw.get("flags", {}), f"{path}.flags"),
        classify=None if classify is None else _field(classify, f"{path}.classify"),
        columns=columns,
        tie_break=tie_break,
        tie_break_descending=descending,
    )


def screen_spec(config: StrategyConfig) -> ScreenSpec:
    """The ``ScreenSpec`` of a rule-screen config (``impl = "rules"``)."""
    if config.impl != RULES_IMPL:
        raise ConfigurationError(f"{config.id} is not a rule screen (impl = {config.impl!r})")
    return parse_screen_spec(config.id, config.rules, config.id)


def check_screen_spec(spec: ScreenSpec, catalog: FieldCatalog, path: str) -> None:
    """Every field exists in the catalogue and every value fits its field's type."""
    catalog.check(Group("all", tuple(c.rule for c in spec.criteria)), f"{path}.criteria")
    for criterion in spec.criteria:
        kind = catalog.fields[criterion.field]
        if criterion.tolerance is not None and kind not in _NUMERIC_TYPES:
            raise _fail(
                f"{path}.criteria.{criterion.id}", f"a tolerance needs a number, not {kind}"
            )
    for section, groups in (("tiers", spec.tiers), ("flags", spec.flags)):
        for name, group in groups:
            catalog.check(group, f"{path}.{section}.{name}")
    for name, field_name in spec.columns:
        catalog.check_field(field_name, f"{path}.columns.{name}")
    if spec.classify is not None:
        kind = catalog.check_field(spec.classify, f"{path}.classify")
        if kind != "str":
            raise _fail(f"{path}.classify", f"needs a label (str) field, not {kind}")
    if spec.tie_break is not None:
        kind = catalog.check_field(spec.tie_break, f"{path}.rank.tie_break")
        if kind not in _NUMERIC_TYPES:
            raise _fail(f"{path}.rank.tie_break", f"needs a numeric field, not {kind}")
