"""The position key of a stored option trade (ADR 0088, design 2.5, G24): one canonical string
built from what the trade *is*, never from the template's id, so an edit of ``templates.toml``
cannot change what a stored row means (a changed template writes new keys).

``resolve_legs`` gives an outcome's legs from its template (``strike_delta`` replaces the delta of
the short delta legs only, a long wing keeps the template's; an option leg without a tenor of its
own takes the outcome's). ``position_key`` is the canonical sorted JSON of the resolved legs, the
collateral rule, the selection parameters (``strike_delta``, ``tenor_days``, ``expiry_cycle``,
``skip_report_in_life``), the entry offset, the ordered exit rule list and the hold cap; two grid
points that differ only in ``take_profit`` are two keys. ``parse_position_key`` is its inverse
(``ParsedKey``), so a stored row round-trips to the spec that wrote it."""

import json
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from algotrade.config.edges.positions.spec import ExitRule, ExitSettings, exit_rules
from algotrade.config.edges.positions.templates import OPTION, Leg, Template, Templates
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.predicates import Group, Rule

if TYPE_CHECKING:
    from algotrade.config.edges.document import Outcome


def resolve_legs(outcome: "Outcome", template: Template) -> tuple[Leg, ...]:
    """The legs ``outcome`` holds: the template's, with ``strike_delta`` in place of the delta of
    each short delta leg (a long wing keeps the template's delta) and the outcome's ``tenor_days``
    on each option leg that names none."""
    legs = []
    for leg in template.legs:
        if leg.kind != OPTION:
            legs.append(leg)
            continue
        delta = leg.delta
        if leg.strike == "delta" and leg.qty < 0 and outcome.strike_delta is not None:
            delta = outcome.strike_delta
        legs.append(replace(leg, delta=delta, tenor_days=leg.tenor_days or outcome.tenor_days))
    return tuple(legs)


@dataclass(frozen=True)
class ParsedKey:
    """What a ``position_key`` says: the resolved ``legs``, ``collateral``, the selection
    parameters, the entry ``offset``, the ordered exit rules and the hold cap."""

    legs: tuple[Leg, ...]
    collateral: str
    strike_delta: float | None
    tenor_days: int | None
    expiry_cycle: str
    skip_report_in_life: bool
    offset: int
    exits: tuple[ExitRule, ...]
    hold: int


def _leg_json(leg: Leg) -> dict[str, Any]:
    return {
        "kind": leg.kind, "qty": leg.qty, "right": leg.right, "strike": leg.strike,
        "delta": leg.delta, "otm_pct": leg.otm_pct, "tenor_days": leg.tenor_days,
    }  # fmt: skip


def _scalar(value: Any) -> Any:
    """A rule value as JSON, one spelling per value: numbers as floats (1 and 1.0 are one key),
    dates as ISO text."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _node_json(node: Rule | Group) -> dict[str, Any]:
    if isinstance(node, Rule):
        value = (
            [_scalar(v) for v in node.value]
            if isinstance(node.value, tuple)
            else _scalar(node.value)
        )
        return {"f": node.field, "o": node.op, "v": value}
    return {"k": node.kind, "c": [_node_json(c) for c in node.children]}


def _node(raw: dict[str, Any]) -> Rule | Group:
    if "f" in raw:
        value = tuple(raw["v"]) if isinstance(raw["v"], list) else raw["v"]
        return Rule(raw["f"], raw["o"], value)
    return Group(raw["k"], tuple(_node(c) for c in raw["c"]))


def _dump(parsed: ParsedKey) -> str:
    doc = {
        "legs": [_leg_json(leg) for leg in parsed.legs],
        "collateral": parsed.collateral,
        "strike_delta": parsed.strike_delta,
        "tenor_days": parsed.tenor_days,
        "expiry_cycle": parsed.expiry_cycle,
        "skip_report_in_life": parsed.skip_report_in_life,
        "offset": parsed.offset,
        "exits": [{"kind": x.kind, "rule": _node_json(x.rule)} for x in parsed.exits],
        "hold": parsed.hold,
    }
    return json.dumps(doc, sort_keys=True, separators=(",", ":"))


def key_of(parsed: ParsedKey) -> str:
    """The canonical key string of ``parsed`` (the inverse of ``parse_position_key``)."""
    return _dump(parsed)


def parsed_key(outcome: "Outcome", hold: int) -> ParsedKey:
    """The ``ParsedKey`` of ``outcome`` held at most ``hold`` sessions. The outcome's ``position``
    must carry its resolved legs (the edge loader fills them, ``PositionSpec.legs``)."""
    spec = outcome.position
    if spec is None or not spec.legs:
        raise ConfigurationError("an outcome with a resolved position has legs to key (loader)")
    return ParsedKey(
        legs=spec.legs,
        collateral=spec.collateral,
        strike_delta=outcome.strike_delta,
        tenor_days=outcome.tenor_days,
        expiry_cycle=spec.expiry_cycle,
        skip_report_in_life=spec.skip_report_in_life,
        offset=outcome.start_offset_sessions,
        exits=exit_rules(spec.exit),
        hold=hold,
    )


def position_key(outcome: "Outcome", hold: int) -> str:
    """The stored ``position_key`` of ``outcome`` held at most ``hold`` sessions."""
    return _dump(parsed_key(outcome, hold))


def parse_position_key(key: str) -> ParsedKey:
    """The spec a stored ``position_key`` was built from (``ConfigurationError`` on a bad key)."""
    try:
        doc = json.loads(key)
        return ParsedKey(
            legs=tuple(Leg(**raw) for raw in doc["legs"]),
            collateral=doc["collateral"],
            strike_delta=doc["strike_delta"],
            tenor_days=doc["tenor_days"],
            expiry_cycle=doc["expiry_cycle"],
            skip_report_in_life=doc["skip_report_in_life"],
            offset=doc["offset"],
            exits=tuple(ExitRule(x["kind"], _group(x["rule"])) for x in doc["exits"]),
            hold=doc["hold"],
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise ConfigurationError(f"not a position key: {key!r}") from exc


def _group(raw: dict[str, Any]) -> Group:
    node = _node(raw)
    if not isinstance(node, Group):
        raise ValueError("an exit rule is a group")
    return node


def _outcome_with_legs(outcome: "Outcome", templates: Templates) -> "Outcome":
    spec = outcome.position
    if spec is None:
        return outcome
    template = templates[spec.template]
    legs = resolve_legs(outcome, template)
    return replace(outcome, position=replace(spec, legs=legs, collateral=template.collateral))


def _apply(outcome: "Outcome", name: str, value: Any, templates: Templates) -> "Outcome":
    """``outcome`` with the case-valued parameter ``name`` set to ``value``, its legs resolved
    again from the (possibly other) template."""
    spec = outcome.position
    assert spec is not None
    if name in ("strike_delta", "tenor_days"):
        outcome = replace(outcome, **{name: value})
    elif name == "expiry_cycle":
        spec = replace(spec, expiry_cycle=str(value))
    elif name == "position":
        spec = replace(spec, template=str(value))
    else:  # take_profit, stop_loss, exit_dte
        settings = spec.exit or ExitSettings()
        spec = replace(spec, exit=replace(settings, **{name: value}))
    return _outcome_with_legs(replace(outcome, position=spec), templates)


def case_points(outcome: "Outcome", templates: Templates) -> tuple["Outcome", ...]:
    """The concrete outcomes a case-valued setup can resolve to (design 2.4): its defaults, then
    one point per value of each case, so the writer stores the union of them (rows are keyed by the
    point, never by the case rule). An outcome without cases: itself."""
    spec = outcome.position
    base = _outcome_with_legs(outcome, templates)
    if spec is None or not spec.cases:
        return (base,)
    found = [base]
    for case in spec.cases:
        values = [case.default, *(c.value for c in case.cases)]
        found += [_apply(base, case.name, v, templates) for v in dict.fromkeys(values)]
    return tuple(found)


def with_legs(edge: Any, templates: Templates) -> Any:
    """``edge`` with the resolved legs and collateral on the ``position`` of its outcome and of
    each variant's (after ``check_edge`` found every template), so ``position_key`` needs no
    template at a reader."""
    variants = tuple(
        replace(v, outcome=_outcome_with_legs(v.outcome, templates)) for v in edge.variants
    )
    return replace(edge, outcome=_outcome_with_legs(edge.outcome, templates), variants=variants)
