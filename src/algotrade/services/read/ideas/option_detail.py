"""An option pick's sections of the idea page (ADR 0083 amendment 2026-11-01 (b), ADR 0088; plan
O4): ``IdeaOption`` and ``load_idea_option``, filled for a pick of a Premium setup at the served
session, derived figures only (no bid or ask leaves the read model):

* the example position (``positions.option_example``: the legs the setup's rule would open on
  the pick's chain at S, their mid, our delta, the net credit and the cash set aside per
  contract), and the setup's declared exits as dollar marks on it (E12b);
* the most you can lose per contract (``quant.options.position.max_loss``: the worst expiry
  payoff on the credit, ``None`` and ``unbounded`` when a naked call has no limit);
* the figures E9 deferred to here, computed in ``quant.options.position`` from the example's own
  legs: the position's theta a day, each leg's chance of finishing in the money, the one-sigma
  day loss; and the calendar flags, ``report_in_life`` (the name's own report between the entry
  and the expiry) and ``ex_div_before_expiry`` (``dividend_schedule.next_ex_date`` read as a
  catalogue field, never the table);
* ``monday_floor``: the premium below which the setup's rule would no longer hold on Monday. No
  setup declares a minimum credit yet (concepts 2.16 EF-G14) and no option verdict stores a
  typical trade, so it is UNKNOWN with that reason, never a number made up here.

Fail closed: an example UNKNOWN (no chain, no legs, case values not yet applied by a run) makes
the section UNKNOWN with its reason and every figure empty; a figure whose input is missing is
UNKNOWN on its own (``risk_unknown``, ``calendar_unknown``), never zero. Reads ``chains/*`` for
the served session only, through the example loader; the bought history never reaches it."""

from dataclasses import dataclass
from datetime import date

import numpy as np

from algotrade.config.edges.positions.templates import SHARES
from algotrade.quant.options import position
from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.context import ReadContext
from algotrade.services.read.evaluation.edges import Edge, parsed_edges
from algotrade.services.read.evaluation.positions.exit_rule import ExitRule
from algotrade.services.read.evaluation.positions.option_example import (
    OptionExample,
    load_option_examples,
)
from algotrade.services.read.events.instrument_events import load_instrument_events
from algotrade.services.read.instruments.features import load_feature_values
from algotrade.services.read.values import Unknown, UnknownCode

OWN_EARNINGS = ("own_earnings", "reference_earnings")
NEXT_EX_DATE = "dividend_schedule.next_ex_date"


@dataclass(frozen=True)
class OptionLegView:
    """One leg of the example: ``right`` (``put`` / ``call``), ``strike``, ``expiry``, ``qty``
    (signed; negative: sold), ``mid`` and our ``delta`` per share, and ``p_itm`` the quoted
    chance it finishes in the money (None: no usable IV)."""

    right: str
    strike: float
    expiry: date
    qty: int
    mid: float
    delta: float | None
    p_itm: float | None


@dataclass(frozen=True)
class IdeaOption:
    """The option sections of one pick. Amounts are dollars per contract (one position), prices
    per share. ``legs`` empty and ``unknown`` set: no example at all. ``exit_rule``: the
    setup's exits (its own ``unknown`` says which part is missing), with the marks of the
    example beside it. ``max_loss`` None: ``unbounded`` says whether it is unlimited."""

    chain_asof: date
    unknown: Unknown | None = None
    legs: tuple[OptionLegView, ...] = ()
    spot: float | None = None
    entry_session: date | None = None
    exit_session: date | None = None
    net_credit: float | None = None
    cash_set_aside: float | None = None
    exit_rule: ExitRule | None = None
    stop_debit: float | None = None
    stop_loss: float | None = None
    take_profit_debit: float | None = None
    exit_dte_date: date | None = None
    max_loss: float | None = None
    unbounded: bool = False
    theta_per_day: float | None = None
    one_sigma_loss: float | None = None
    risk_unknown: Unknown | None = None
    report_in_life: bool | None = None
    report_date: date | None = None
    ex_div_before_expiry: bool | None = None
    ex_div_date: date | None = None
    calendar_unknown: Unknown | None = None
    monday_floor: float | None = None
    floor_unknown: Unknown | None = None


def _finite(value: float | None) -> float | None:
    return value if value is not None and np.isfinite(value) else None


def _views(example: OptionExample) -> tuple[OptionLegView, ...]:
    spot = example.spot
    if spot is None:
        return ()
    day = example.chain_asof
    strikes = np.array([leg.strike for leg in example.legs], dtype=np.float64)
    ivs = np.array([np.nan if leg.iv is None else leg.iv for leg in example.legs])
    days = np.array([(leg.expiry - day).days for leg in example.legs], dtype=np.float64)
    calls = np.array([leg.right.upper().startswith("C") for leg in example.legs], dtype=bool)
    chance = position.p_itm(spot, strikes, ivs, days, calls)
    return tuple(
        OptionLegView(
            "call" if calls[i] else "put", leg.strike, leg.expiry, leg.qty, leg.mid, leg.delta,
            _finite(float(chance[i])),
        )
        for i, leg in enumerate(example.legs)
    )  # fmt: skip


def _risk(
    example: OptionExample, shares: float
) -> tuple[float | None, bool, float | None, float | None, Unknown | None]:
    """Max loss, unbounded, theta, one-sigma loss, and the reason a part is missing."""
    spot, credit = example.spot, example.net_credit
    qty = np.array([leg.qty for leg in example.legs], dtype=np.float64)
    strike = np.array([leg.strike for leg in example.legs], dtype=np.float64)
    calls = np.array([leg.right.upper().startswith("C") for leg in example.legs], dtype=bool)
    held = shares if example.share_entry_close is not None else 0.0
    entry = example.share_entry_close or 0.0
    raw = position.max_loss(
        qty, strike, calls, float("nan") if credit is None else credit, held, entry
    )
    unbounded = raw is None and credit is not None
    lost = raw if raw is not None and np.isfinite(raw) else None
    day = example.chain_asof
    ivs = np.array([np.nan if leg.iv is None else leg.iv for leg in example.legs])
    theta = np.array([np.nan if leg.theta is None else leg.theta for leg in example.legs])
    days = np.array([(leg.expiry - day).days for leg in example.legs], dtype=np.float64)
    day_theta = _finite(position.position_theta(qty, theta))
    sigma = _finite(position.one_sigma_day_loss(spot or 0.0, qty, strike, calls, ivs, days, held))
    parts = (("theta", day_theta), ("implied volatility", sigma), ("net credit", lost))
    missing = [
        name
        for name, found in parts
        if found is None and not (name == "net credit" and unbounded)
    ]  # fmt: skip
    why = None
    if missing:
        text = f"the chain at {day} has no {' or '.join(missing)} for a leg of the example"
        why = Unknown(UnknownCode.NO_ROW, run_cause(example.edge_id, text, day))
    return lost, unbounded, day_theta, sigma, why


def _calendar(
    ctx: ReadContext, example: OptionExample, iid: str
) -> tuple[bool | None, date | None, bool | None, date | None, Unknown | None]:
    """Whether the name reports, and goes ex-dividend, between the entry and the expiry; the
    first reason a part is unknown otherwise (each flag still says on its own that it is not
    known)."""
    expiry = min(leg.expiry for leg in example.legs)
    day = ctx.session.date
    found = load_instrument_events(ctx, [iid], days=(expiry - day).days + 1).get(iid)
    report: bool | None = None
    report_date: date | None = None
    unknown: Unknown | None = None
    if found is None:
        text = f"{iid} has no events read for {day}"
        unknown = Unknown(UnknownCode.NOT_STORED, run_cause(iid, text, day))
    else:
        gap = next(
            (g for g in found.gaps if g.part in OWN_EARNINGS and g.instrument_id == iid), None
        )
        opens = example.entry_session or day
        when = [e.date for e in found.ahead if e.kind in OWN_EARNINGS and opens <= e.date <= expiry]
        report = bool(when) if gap is None else None
        report_date = min(when) if when else None
        unknown = None if gap is None else gap.unknown
    cell = load_feature_values(ctx, [iid], [NEXT_EX_DATE]).get(iid, ())
    ex_on: date | None = None
    ex: bool | None = None
    if cell and cell[0].value is not None:
        ex_on = date.fromisoformat(str(cell[0].value)[:10])
        ex = (example.entry_session or day) < ex_on <= expiry
    elif cell:
        unknown = unknown or cell[0].unknown
    return report, report_date, ex, ex_on, unknown


def load_idea_option(
    ctx: ReadContext, edge: Edge, iid: str, rule: ExitRule | None = None
) -> IdeaOption:
    """The option sections of ``iid``'s pick by ``edge`` at ``ctx.session``; the example is read
    through ``load_option_examples`` (one chain read for the pick). ``rule``: the exit rule the
    page already holds, shown when the example has none of its own."""
    day = ctx.session.date
    doc = next((d for d in parsed_edges(ctx, ctx.user.user_id) if d.id == edge.id), None)
    outcome = None if doc is None else doc.outcome
    spec = None if outcome is None else outcome.position
    if outcome is None or spec is None:
        text = f"{edge.id} declares no option position"
        return IdeaOption(day, Unknown(UnknownCode.NOT_APPLICABLE, run_cause(edge.id, text, day)))
    (example,) = load_option_examples(ctx, edge, outcome, [iid])
    if example.unknown is not None or not example.legs or example.spot is None:
        return IdeaOption(
            day,
            example.unknown
            or Unknown(UnknownCode.NO_ROW, run_cause(edge.id, "no example position", day)),
        )
    shares = float(sum(leg.qty for leg in spec.legs if leg.kind == SHARES))
    lost, unbounded, theta, sigma, risk_unknown = _risk(example, shares)
    report, report_date, ex, ex_on, cal_unknown = _calendar(ctx, example, iid)
    floor_text = (
        f"{edge.id} declares no minimum credit and no verdict stores a typical trade of the "
        f"setup yet, so no premium floor is stored"
    )
    credit = example.net_credit
    return IdeaOption(
        chain_asof=example.chain_asof,
        legs=_views(example),
        spot=example.spot,
        entry_session=example.entry_session,
        exit_session=example.exit_session,
        net_credit=credit,
        cash_set_aside=None
        if example.collateral is None
        else example.collateral * position.MULTIPLIER,
        exit_rule=example.rule or rule,
        stop_debit=example.stop_debit,
        stop_loss=example.stop_loss,
        take_profit_debit=example.take_profit_debit,
        exit_dte_date=example.exit_dte_date,
        max_loss=lost,
        unbounded=unbounded,
        theta_per_day=theta,
        one_sigma_loss=sigma,
        risk_unknown=risk_unknown,
        report_in_life=report,
        report_date=report_date,
        ex_div_before_expiry=ex,
        ex_div_date=ex_on,
        calendar_unknown=cal_unknown,
        floor_unknown=Unknown(UnknownCode.NOT_APPLICABLE, run_cause(edge.id, floor_text, day)),
    )
