"""``PositionSpec``: what an outcome adds to a position template (ADR 0088, design 2.4, 2.4a): the
``position`` key naming the template, the option parameters beside it (``expiry_cycle``,
``skip_report_in_life``, ``book``) and the declared exits of ``[outcome.exit]`` (``take_profit``,
``stop_loss``, ``exit_dte``). ``strike_delta`` and ``tenor_days`` stay the outcome's own keys.
Parsed here, checked against the site's templates where the edge loads (``check_outcome``); the
engine that reads it is a later slice. ``when`` of ``[outcome.exit]`` (a rule over position-level
and catalogue fields), the case values and the three exit settings compiled to position rules
(``exit_rules``) are here too; the catalogue check of every rule is ``check_rules``."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from algotrade.config.edges.positions import grid
from algotrade.config.edges.positions.cases import (
    EXPIRY_CYCLES,
    CaseValue,
    canonical,
    when_of,
)
from algotrade.config.edges.positions.fields import fields_for
from algotrade.config.edges.positions.templates import (
    RETURN_KINDS,
    SIDE_TEMPLATES,
    Templates,
    check_known,
)
from algotrade.config.site.fields import Table
from algotrade.config.strategy.catalog import FieldCatalog
from algotrade.config.strategy.levels import CASE, ENTRY, EXIT, GATE
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.fields import is_position_field
from algotrade.core.model.ids import validate_id
from algotrade.core.model.predicates import Group, Rule

if TYPE_CHECKING:
    from algotrade.config.edges.document import Outcome

KEYS = ("position", "expiry_cycle", "skip_report_in_life", "book", "exit")
EXIT_KEYS = ("take_profit", "stop_loss", "exit_dte", "when")
OPTION_KIND = "option_pnl"
MAX_EXIT_DTE = 400


@dataclass(frozen=True)
class ExitSettings:
    """The declared exits, each ``None`` when not set (design 2.4a: closes only)."""

    take_profit: float | None = None  # close when this share of the credit is captured
    stop_loss: float | None = None  # close when the loss reaches this multiple of the credit
    exit_dte: int | None = None  # close at this many calendar days to expiry
    when: Group | None = None  # an exit condition (use site ``exit``), canonical form


@dataclass(frozen=True)
class PositionSpec:
    template: str
    expiry_cycle: str = "monthly"
    skip_report_in_life: bool = False
    book: bool = False
    exit: ExitSettings | None = None
    cases: tuple[
        CaseValue, ...
    ] = ()  # the case-valued parameters (their defaults are the literals)


def spec_of(
    o: Table, kind: str, offset: int, cases: tuple[CaseValue, ...] = ()
) -> PositionSpec | None:
    """The outcome's ``PositionSpec`` (None without ``position``: its other keys are refused).
    The entry offset of a position is at least 1: the screen and the gate are known only after
    the decision session's close (G-H1)."""
    if "position" not in o.names():
        named = [k for k in KEYS[1:] if k in o.names()] + ["cases" for _ in cases]
        if named:
            raise ConfigurationError(f"{o.where} {named[0]}: needs a position")
        return None
    if kind not in (*RETURN_KINDS, OPTION_KIND):
        raise ConfigurationError(
            f"{o.where} position: only an excess_return, hit_target or option_pnl outcome has one"
        )
    if "structure" in o.names():
        raise ConfigurationError(
            f"{o.where} position: not with structure (the older option kinds' enum)"
        )
    if offset < 1:
        raise ConfigurationError(
            f"{o.where} start_offset_sessions: a position enters after the decision session's "
            f"close (>= 1), got {offset}"
        )
    return PositionSpec(
        template=validate_id("position", o.text("position", "")),
        expiry_cycle=o.choice("expiry_cycle", "monthly", EXPIRY_CYCLES),
        skip_report_in_life=o.boolean("skip_report_in_life", False),
        book=o.boolean("book", False),
        exit=_exit(o),
        cases=cases,
    )


def gate_of(t: Table) -> Group | None:
    """The setup's gate as a parsed rule group (structure only; the catalogue check and the
    decision are E7's, which is when ``check_edge`` stops refusing it)."""
    raw = t.raw("gate")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ConfigurationError(f"{t.where} gate: expected a rule table, got {raw!r}")
    return when_of(raw, f"{t.where} gate")


def _exit(o: Table) -> ExitSettings | None:
    if "exit" not in o.names():
        return None
    t = o.table("exit", EXIT_KEYS)
    stop, dte = t.number("stop_loss", None, 0), t.integer("exit_dte", -1, -1)
    profit = t.number("take_profit", None, 0)
    if profit is not None and profit > 1:
        raise ConfigurationError(f"{t.where} take_profit: expected a share of the credit, 0 to 1")
    if dte > MAX_EXIT_DTE:
        raise ConfigurationError(f"{t.where} exit_dte: at most {MAX_EXIT_DTE} days")
    when = when_of(t.raw("when"), f"{t.where} when") if "when" in t.names() else None
    # 0 is "not set" (a grid axis spells off as 0)
    settings = ExitSettings(profit or None, stop or None, dte if dte > 0 else None, when)
    if settings == ExitSettings():
        raise ConfigurationError(f"{t.where}: names none of {list(EXIT_KEYS)}")
    return settings


def check_outcome(outcome: "Outcome", where: str, templates: Templates) -> None:
    """The template exists and fits the outcome's kind: an ``option_pnl`` position has an option
    leg, a return outcome's is shares of its own side; exits and option parameters are for an
    option position."""
    spec = outcome.position
    if spec is None:
        return
    check_known(where, "position", (spec.template,), templates)
    template = templates[spec.template]
    kind = outcome.kind
    if (kind == OPTION_KIND) != template.has_option:
        raise ConfigurationError(
            f"{where} position: {spec.template!r} does not fit a {kind} outcome "
            f"(option_pnl takes a template with an option leg, a return outcome shares only)"
        )
    if outcome.strike_delta is not None and not any(leg.strike == "delta" for leg in template.legs):
        raise ConfigurationError(
            f"{where} strike_delta: {spec.template!r} has no leg chosen by delta"
        )
    if template.share_only:
        if spec.exit is not None or spec.book or spec.skip_report_in_life:
            raise ConfigurationError(
                f"{where} position: exit, book and skip_report_in_life are for an option position"
            )
        if SIDE_TEMPLATES.get(outcome.side) != (spec.template,):
            raise ConfigurationError(
                f"{where} position: {spec.template!r} is not the position of side {outcome.side!r}"
            )


def check_edge(edge: Any, where: str, templates: Templates) -> None:
    """The position parts of a loaded edge against the site's templates: each outcome's
    template, the ``position:<id>`` baselines, and a grid only over an option position (its ids
    never clash with the edge's variants or ``main``)."""
    for outcome in (edge.outcome, *(v.outcome for v in edge.variants)):
        check_outcome(outcome, where, templates)
    check_known(where, "baselines", edge.position_baselines, templates)
    for outcome in (edge.outcome, *(v.outcome for v in edge.variants)):
        pending = [
            (what, slice_)
            for what, slice_, used in (
                ("entry", "E13", outcome.entry is not None),
                ("case values", "E13", outcome.position is not None and outcome.position.cases),
            )
            if used
        ]
        if pending:
            raise ConfigurationError(
                f"{where} {pending[0][0]}: not applied by any run yet ({pending[0][1]}), so the "
                f"edge would be measured without it"
            )
    if edge.gate is not None:
        raise ConfigurationError(
            f"{where} gate: not applied by any run yet (E7), so a gated edge would be "
            f"measured ungated"
        )
    if not edge.variant_grid:
        return
    if edge.outcome.kind != OPTION_KIND or edge.outcome.position is None:
        raise ConfigurationError(f"{where} variant_grid: only an option_pnl position has a grid")
    taken = {"main", *(v.id for v in edge.variants)}
    clash = sorted(taken & set(grid.grid_ids(edge.variant_grid)))
    if clash:
        raise ConfigurationError(f"{where} variant_grid: ids {clash} clash with a variant")


KIND_TAKE_PROFIT, KIND_STOP_LOSS, KIND_EXIT_DTE, KIND_CONDITION = (
    "TAKE_PROFIT", "STOP_LOSS", "EXIT_DTE", "CONDITION",
)  # fmt: skip


@dataclass(frozen=True)
class ExitRule:
    """One entry of a position's ordered exit list: the ``exit_kind`` it gives and its rule."""

    kind: str
    rule: Group


def exit_rules(exit: ExitSettings | None) -> tuple[ExitRule, ...]:
    """The exit settings compiled, in the declared order, to rules over position-level fields
    (take profit, stop loss, DTE) followed by ``when``: the engine's one exit path. Several TRUE
    at one close: the first listed wins."""
    if exit is None:
        return ()
    found: list[ExitRule] = []
    if exit.take_profit is not None:
        rule = Rule("position.profit_share_of_credit", "gte", exit.take_profit)
        found.append(ExitRule(KIND_TAKE_PROFIT, Group("all", (rule,))))
    if exit.stop_loss is not None:
        rule = Rule("position.profit_share_of_credit", "lte", -exit.stop_loss)
        found.append(ExitRule(KIND_STOP_LOSS, Group("all", (rule,))))
    if exit.exit_dte is not None:
        found.append(
            ExitRule(KIND_EXIT_DTE, Group("all", (Rule("position.dte", "lte", exit.exit_dte),)))
        )
    if exit.when is not None:
        found.append(ExitRule(KIND_CONDITION, canonical(exit.when)))
    return tuple(found)


def exit_delay(rule: Group) -> int:
    """Sessions after close t a rule observed at t acts: 0 when it names only position-level
    fields (they are t's own closing marks), else 1 (nightly features of t exist only after t's
    close, the same reason an entry offset is at least 1)."""
    return 0 if all(is_position_field(r.field) for r in rule.rules()) else 1


def check_rules(edge: Any, where: str, catalog: FieldCatalog, templates: Templates) -> None:
    """Every rule of an edge against ``catalog`` at its use site: the gate at ``gate``, each
    outcome's entry condition at ``entry``, case rules at ``case`` and the exit condition at
    ``exit`` (with the ``position.*`` fields that apply to its template's legs); a ``position``
    case chooses among templates of one kind."""
    if edge.gate is not None:
        catalog.check(edge.gate, f"{where} gate", GATE)
    for outcome in (edge.outcome, *(v.outcome for v in edge.variants)):
        if outcome.entry is not None:
            catalog.check(outcome.entry.when, f"{where} outcome.entry.when", ENTRY)
        spec = outcome.position
        if spec is None:
            continue
        for case_value in spec.cases:
            for case in case_value.cases:
                catalog.check(case.when, f"{where} outcome.{case_value.name}.cases", CASE)
        _check_position_cases(spec, where, templates)
        if spec.exit is not None and spec.exit.when is not None and spec.template in templates:
            own = {**catalog.levels, "position": fields_for(templates[spec.template])}
            replace(catalog, levels=own).check(spec.exit.when, f"{where} outcome.exit.when", EXIT)


def _check_position_cases(spec: PositionSpec, where: str, templates: Templates) -> None:
    for case_value in spec.cases:
        if case_value.name != "position":
            continue
        named = (case_value.default, *(c.value for c in case_value.cases))
        check_known(where, "position cases", tuple(str(n) for n in named), templates)
        if len({templates[str(n)].has_option for n in named}) > 1:
            raise ConfigurationError(
                f"{where} position: the cases choose among templates of one kind (all with an "
                f"option leg, or all shares), so a setup's trades come from one grain"
            )
