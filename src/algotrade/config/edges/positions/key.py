"""The position key of a stored option trade (ADR 0088, design 2.5, G24): one canonical string
built from what the trade *is*, never from the template's id, so an edit of ``templates.toml``
cannot change what a stored row means (a changed template writes new keys).

``resolve_legs`` gives an outcome's legs from its template (``strike_delta`` replaces the delta of
the short delta legs only, a long wing keeps the template's; an option leg without a tenor of its
own takes the outcome's). ``position_key`` is the canonical sorted JSON of the resolved legs, the
collateral rule, the selection parameters (``strike_delta``, ``tenor_days``, ``expiry_cycle``,
``skip_report_in_life``), the entry offset, the ordered exit rule list and the hold cap; two grid
points that differ only in ``take_profit`` are two keys. ``parse_position_key`` is its inverse
(``ParsedKey``), so a stored row round-trips to the spec that wrote it. ``share_position_key`` is
the same string for a share position with declared exits (E3c-2): its legs, the entry offset, its
side's ordered exit rules (``share_exit_rules``: moves of the entry price, not credit shares) and
the hold cap, the option parameters empty, so a share and an option trade never share a key.
``grid_outcomes`` gives the outcome of each ``[[variant_grid]]`` point (the writer stores them,
the harness reads them)."""

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from itertools import product
from typing import TYPE_CHECKING, Any

from algotrade.config.edges.positions.grid import points
from algotrade.config.edges.positions.spec import (
    ExitRule,
    ExitSettings,
    exit_rules,
    share_exit_rules,
)
from algotrade.config.edges.positions.templates import OPTION, Leg, Template, Templates
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.predicates import Group, Rule

if TYPE_CHECKING:
    from algotrade.config.edges.document import Outcome
    from algotrade.config.edges.positions.cases import CaseValue


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


def share_position_key(outcome: "Outcome", hold: int) -> str:
    """The stored ``position_key`` of a share position (a share-only template, legs resolved by the
    loader) held at most ``hold`` sessions: its exits compiled for its ``side``, no option
    parameters (``ConfigurationError`` without resolved share legs)."""
    spec = outcome.position
    if spec is None or not spec.legs or any(leg.kind == OPTION for leg in spec.legs):
        raise ConfigurationError("a share position key needs resolved share legs (loader)")
    return _dump(
        ParsedKey(
            legs=spec.legs, collateral=spec.collateral, strike_delta=None, tenor_days=None,
            expiry_cycle="", skip_report_in_life=False, offset=outcome.start_offset_sessions,
            exits=share_exit_rules(spec.exit, outcome.side), hold=hold,
        )
    )  # fmt: skip


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


def with_template(outcome: "Outcome", template_id: str, templates: Templates) -> "Outcome":
    """``outcome`` holding the template ``template_id`` instead, its legs and collateral resolved
    from it (a position baseline's outcome, ``services/evaluation/cross_section/baselines``)."""
    return _apply(outcome, "position", template_id, templates)


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
    """The concrete outcomes a case-valued setup can resolve to (design 2.4): one point per
    combination of the cases' values (their defaults first), so the writer stores every point a
    name can resolve to at D, two cases away from their defaults included (rows are keyed by the
    point, never by the case rule). An outcome without cases: itself."""
    spec = outcome.position
    base = _outcome_with_legs(outcome, templates)
    if spec is None or not spec.cases:
        return (base,)
    return tuple(case_point(base, values, templates) for values in case_combinations(spec.cases))


def case_combinations(cases: Sequence["CaseValue"]) -> list[tuple[Any, ...]]:
    """Every combination of the cases' values (each case's default first), in ``cases`` order."""
    choices = [list(dict.fromkeys([c.default, *(x.value for x in c.cases)])) for c in cases]
    return list(product(*choices))


def case_point(outcome: "Outcome", values: Sequence[Any], templates: Templates) -> "Outcome":
    """``outcome`` at one combination of its case values (``values``, in the order of
    ``position.cases``): the point a name resolves to at D, keyed as the writer keyed it."""
    spec = outcome.position
    assert spec is not None
    for case, value in zip(spec.cases, values, strict=True):
        outcome = _apply(outcome, case.name, value, templates)
    return outcome


def grid_outcomes(edge: Any, templates: Templates) -> tuple[tuple[str, "Outcome"], ...]:
    """``(point id, outcome)`` of every point of ``edge``'s ``[[variant_grid]]`` tables, in their
    fixed order: the edge's own outcome with the point's parameters set and its legs resolved
    again (``points``; none: ``()``)."""
    return tuple(
        (p.id, _with_values(edge.outcome, p.values, templates))
        for g in edge.variant_grid
        for p in points(g)
    )


def _with_values(
    outcome: "Outcome", values: tuple[tuple[str, float], ...], templates: Templates
) -> "Outcome":
    for name, value in values:
        outcome = _apply(outcome, name, value, templates)
    return _loaded(outcome, templates)  # its own case points' keys, never the base point's


def with_legs(edge: Any, templates: Templates) -> Any:
    """``edge`` with the resolved legs and collateral on the ``position`` of its outcome and of
    each variant's (after ``check_edge`` found every template), so ``position_key`` needs no
    template at a reader."""
    variants = tuple(replace(v, outcome=_loaded(v.outcome, templates)) for v in edge.variants)
    return replace(edge, outcome=_loaded(edge.outcome, templates), variants=variants)


def _loaded(outcome: "Outcome", templates: Templates) -> "Outcome":
    """``outcome`` with its legs and, when it has case values, the key of every point they can
    resolve to at every hold (``PositionSpec.points``), so a reader keys a name's point without
    the templates."""
    base = _outcome_with_legs(outcome, templates)
    spec = base.position
    if spec is None or not spec.cases:
        return base
    points = tuple(
        (values, hold, position_key(case_point(base, values, templates), hold))
        for values in case_combinations(spec.cases)
        for hold in base.horizon_sessions
    )
    return replace(base, position=replace(spec, points=points))
