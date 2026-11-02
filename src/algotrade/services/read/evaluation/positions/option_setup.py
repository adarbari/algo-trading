"""The option setup page's read object (ADR 0088, plan O1): ``OptionSetup`` and
``load_option_setup``.

Two sections of one setup, each with its own reason when it is not there:

- ``rules``: the setup's option position as its document declares it (the rows of the page:
  when it trades, what it picks, what it sells and how the strike is chosen, the expiry, the
  collateral, the declared exits and what happens if the option is assigned), as structured values
  the browser formats: the template's legs (each with its strike rule by delta, at the money or
  percent out of the money, and its own tenor), the outcome's tenor and entry offset, the expiry
  cycle, whether it skips a report in the option's life, the collateral rule and the declared
  ``take_profit`` / ``stop_loss`` / ``exit_dte``. A parameter chosen by case for each pick is named
  in ``case_valued``, never given a value. A share setup has none (``NOT_APPLICABLE``), and
  ``position_kind`` says which it is (``shares`` | ``options``).
- ``evidence`` (``option_evidence.py``): the history on the cash set aside, from the stored
  ledger; None for a share setup.

The document is the viewer's (``parsed_edges``: a site edge with their layer over it), the edge
is served only to a viewer who holds the licence of its evidence (``load_edge``). Nothing here
judges: no verdict is made or stored by this read."""

from dataclasses import dataclass

from algotrade.config.edges import document
from algotrade.config.edges.positions.spec import OPTION_KIND
from algotrade.config.edges.positions.templates import holds_options
from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.context import ReadContext
from algotrade.services.read.evaluation.edges import Edge, load_edge, parsed_edges
from algotrade.services.read.evaluation.positions.option_evidence import (
    OptionEvidence,
    load_option_evidence,
)
from algotrade.services.read.values import Unknown, UnknownCode

SHARES, OPTIONS = "shares", "options"


@dataclass(frozen=True)
class LegRule:
    """One leg of the template: ``kind`` (``shares`` | ``option``), ``qty`` signed (negative:
    sold), and for an option its ``right`` (P | C), ``strike`` rule (``delta`` | ``atm`` |
    ``otm_pct``) with its ``delta`` or ``otm_pct`` (a fraction), and its own ``tenor_days`` (None:
    the setup's)."""

    kind: str
    qty: int
    right: str | None
    strike: str | None
    delta: float | None
    otm_pct: float | None
    tenor_days: int | None


@dataclass(frozen=True)
class OptionRules:
    """The declared position. ``schedule``: when the setup decides (the edge's own words, e.g.
    ``every_session``); ``start_offset_sessions``: the entry that many sessions after the decision;
    ``tenor_days``: the days to expiry sought; ``expiry_cycle``; ``collateral`` (``cash_secured`` |
    ``max_loss`` | ``regt`` | ``notional``); the declared exits (None: not declared; a
    ``stop_loss`` a multiple of the credit, ``take_profit`` a share of it, ``exit_dte`` calendar
    days to expiry) and ``exit_condition_fields`` of its exit condition; ``case_valued``: the
    parameters chosen by case for each pick."""

    template: str
    legs: tuple[LegRule, ...]
    collateral: str
    schedule: str
    start_offset_sessions: int
    tenor_days: int | None
    expiry_cycle: str
    skip_report_in_life: bool
    take_profit: float | None
    stop_loss: float | None
    exit_dte: int | None
    exit_condition_fields: tuple[str, ...]
    case_valued: tuple[str, ...]


@dataclass(frozen=True)
class OptionSetup:
    """The option setup page of ``edge_id``: its ``position_kind`` and, for an option setup, its
    ``rules`` (None with ``rules_unknown``) and ``evidence``; a share setup has neither section
    (``evidence`` None, ``rules_unknown`` ``NOT_APPLICABLE``)."""

    edge_id: str
    position_kind: str
    rules: OptionRules | None
    rules_unknown: Unknown | None
    evidence: OptionEvidence | None


def _rules(edge: Edge, doc: document.Edge) -> OptionRules | Unknown:
    outcome = doc.outcome
    spec = outcome.position
    if spec is None or not spec.legs:
        why = f"{edge.id} predates the position templates: its legs are not declared"
        return Unknown(UnknownCode.NOT_APPLICABLE, run_cause(edge.id, why))
    exits = spec.exit
    return OptionRules(
        template=spec.template,
        legs=tuple(
            LegRule(
                leg.kind, leg.qty, leg.right, leg.strike, leg.delta, leg.otm_pct, leg.tenor_days
            )
            for leg in spec.legs
        ),
        collateral=spec.collateral,
        schedule=edge.schedule,
        start_offset_sessions=outcome.start_offset_sessions,
        tenor_days=outcome.tenor_days,
        expiry_cycle=spec.expiry_cycle,
        skip_report_in_life=spec.skip_report_in_life,
        take_profit=exits.take_profit if exits else None,
        stop_loss=exits.stop_loss if exits else None,
        exit_dte=exits.exit_dte if exits else None,
        exit_condition_fields=(
            tuple(sorted({r.field for r in exits.when.rules()})) if exits and exits.when else ()
        ),
        case_valued=tuple(sorted(c.name for c in spec.cases)),
    )


def load_option_setup(ctx: ReadContext, edge_id: str) -> OptionSetup | None:
    """The option setup page of ``edge_id`` at ``ctx.session``; None: the viewer has no such edge
    (or lacks the licence of its evidence)."""
    edge = load_edge(ctx, edge_id)
    doc = next((e for e in parsed_edges(ctx, ctx.user.user_id) if e.id == edge_id), None)
    if edge is None or doc is None:
        return None
    if not holds_options(doc.outcome, ctx.configs) and doc.outcome.kind != OPTION_KIND:
        why = f"{edge_id} holds shares, not options"
        unknown = Unknown(UnknownCode.NOT_APPLICABLE, run_cause(edge_id, why))
        return OptionSetup(edge_id, SHARES, None, unknown, None)
    rules = _rules(edge, doc)
    evidence = load_option_evidence(ctx, edge)
    if isinstance(rules, Unknown):
        return OptionSetup(edge_id, OPTIONS, None, rules, evidence)
    return OptionSetup(edge_id, OPTIONS, rules, None, evidence)
