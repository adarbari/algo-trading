"""``PositionSpec``: what an outcome adds to a position template (ADR 0088, design 2.4, 2.4a): the
``position`` key naming the template, the option parameters beside it (``expiry_cycle``,
``skip_report_in_life``, ``book``) and the declared exits of ``[outcome.exit]`` (``take_profit``,
``stop_loss``, ``exit_dte``). ``strike_delta`` and ``tenor_days`` stay the outcome's own keys.
Parsed here, checked against the site's templates where the edge loads (``check_outcome``); the
engine that reads it is a later slice. ``when`` of ``[outcome.exit]`` and ``[outcome.entry]`` are
parsed with the rules (E2r)."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from algotrade.config.edges.positions import grid
from algotrade.config.edges.positions.templates import (
    RETURN_KINDS,
    SIDE_TEMPLATES,
    Templates,
    check_known,
)
from algotrade.config.site.fields import Table
from algotrade.config.strategy.schema import Group, parse_group
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id

if TYPE_CHECKING:
    from algotrade.config.edges.document import Outcome

KEYS = ("position", "expiry_cycle", "skip_report_in_life", "book", "exit")
EXIT_KEYS = ("take_profit", "stop_loss", "exit_dte")
EXPIRY_CYCLES = ("monthly", "weekly", "any")
OPTION_KIND = "option_pnl"
MAX_EXIT_DTE = 400


@dataclass(frozen=True)
class ExitSettings:
    """The declared exits, each ``None`` when not set (design 2.4a: closes only)."""

    take_profit: float | None = None  # close when this share of the credit is captured
    stop_loss: float | None = None  # close when the loss reaches this multiple of the credit
    exit_dte: int | None = None  # close at this many calendar days to expiry


@dataclass(frozen=True)
class PositionSpec:
    template: str
    expiry_cycle: str = "monthly"
    skip_report_in_life: bool = False
    book: bool = False
    exit: ExitSettings | None = None


def spec_of(o: Table, kind: str, offset: int) -> PositionSpec | None:
    """The outcome's ``PositionSpec`` (None without ``position``: its other keys are refused).
    The entry offset of a position is at least 1: the screen and the gate are known only after
    the decision session's close (G-H1)."""
    if "position" not in o.names():
        named = [k for k in KEYS[1:] if k in o.names()]
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
    )


def gate_of(t: Table) -> Group | None:
    """The setup's gate as a parsed rule group (structure only; the catalogue check and the
    decision are E7's, which is when ``check_edge`` stops refusing it)."""
    raw = t.raw("gate")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ConfigurationError(f"{t.where} gate: expected a rule table, got {raw!r}")
    return parse_group(raw, f"{t.where} gate")


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
    # 0 is "not set" (a grid axis spells off as 0)
    settings = ExitSettings(profit or None, stop or None, dte if dte > 0 else None)
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
