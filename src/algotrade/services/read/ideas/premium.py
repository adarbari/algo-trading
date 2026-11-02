"""The option row of a Premium idea (O3, ADR 0083 amendment (d), ADR 0088 design 2.8):
``PremiumOption`` and ``load_premium_options``.

For each idea on the Premium tab, the example position its setup would open at the served session
S (``positions.option_example.load_option_examples``: the harness's own leg rule over S's stored
chain, never the bought history) shown as derived figures only (ADR 0083 amendment, decision B):
each leg's right, strike, expiry, signed quantity and our mid; the net credit and the collateral
per contract (the template's collateral, ``SHARES_PER_CONTRACT`` shares); the return on
collateral (credit over collateral); and the chance of assignment, the risk-neutral chance at least
one sold leg ends in the money at the expiry (``quant.options.position.assignment_chance``, the
idea page's own maths, over each leg's stored IV and calendar days from S to its expiry).
Never a bid, ask, last or size.

Point in time: everything is read at S (the chain, its spot and the exit rule's hold, bounded by
the canonical run committed on or before S). The licence filter is the one Ideas already applies:
a setup whose evidence the viewer lacks the licence of is never a qualifying setup
(``load_edges``, ADR 0084), and the chain figures are stored open data (Cboe). Nothing is filled:
no example is an ``Unknown`` with its reason (``unknown``), and a figure that cannot be computed
(a leg with no stored IV, no collateral) is None with its own ``Unknown``."""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np

from algotrade.engines.structures.trades import SHARES_PER_CONTRACT
from algotrade.quant.options.position import assignment_chance
from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.context import ReadContext
from algotrade.services.read.evaluation.edges import parsed_edges
from algotrade.services.read.evaluation.positions.option_example import (
    OptionExample,
    load_option_examples,
)
from algotrade.services.read.ideas.setups import QualifyingSetup
from algotrade.services.read.values import Unknown, UnknownCode

CALL = "C"  # a call leg's right


@dataclass(frozen=True)
class PremiumLeg:
    """One leg of the example: ``right`` P or C, ``qty`` signed (negative: sold), ``mid`` per share
    (our mid of the stored close quote)."""

    right: str
    strike: float
    expiry: date
    qty: int
    mid: float


@dataclass(frozen=True)
class PremiumOption:
    """The option row of one Premium idea. ``credit`` (positive: received) and ``collateral`` per
    contract; ``return_on_collateral`` their ratio; ``assignment_chance`` in [0, 1]; ``expiry``
    the nearest leg's. ``unknown``: why there is no example (every figure empty); a single figure
    that is None says why in ``chance_unknown`` or ``collateral_unknown``."""

    edge_id: str
    instrument_id: str
    legs: tuple[PremiumLeg, ...] = ()
    expiry: date | None = None
    credit: float | None = None
    collateral: float | None = None
    return_on_collateral: float | None = None
    assignment_chance: float | None = None
    unknown: Unknown | None = None
    chance_unknown: Unknown | None = None
    collateral_unknown: Unknown | None = None


def _gap(edge_id: str, why: str) -> Unknown:
    return Unknown(UnknownCode.NULL, run_cause(edge_id, why))


def _chance(example: OptionExample, day: date) -> tuple[float | None, Unknown | None]:
    legs = example.legs
    if example.spot is None or not any(leg.qty < 0 for leg in legs):
        return None, _gap(example.edge_id, "no sold leg or no underlying price at the session")
    if any(leg.iv is None for leg in legs if leg.qty < 0):
        return None, _gap(example.edge_id, "a sold leg has no stored implied volatility")
    found = assignment_chance(
        example.spot,
        np.array([leg.strike for leg in legs]),
        np.array([np.nan if leg.iv is None else leg.iv for leg in legs]),
        np.array([(leg.expiry - day).days for leg in legs], dtype=np.float64),
        np.array([leg.right == CALL for leg in legs]),
        np.array([leg.qty for leg in legs]),
    )
    if math.isnan(found):  # an IV or the days to expiry are not positive
        return None, _gap(example.edge_id, "the implied volatility or the time to expiry is zero")
    return found, None


def premium_option(example: OptionExample, day: date) -> PremiumOption:
    """The row of one example at session ``day``."""
    if example.unknown is not None or not example.legs:
        unknown = example.unknown or _gap(example.edge_id, "the example has no option legs")
        return PremiumOption(example.edge_id, example.underlying_id, unknown=unknown)
    legs = tuple(PremiumLeg(x.right, x.strike, x.expiry, x.qty, x.mid) for x in example.legs)
    credit = None if example.net_credit is None else example.net_credit * SHARES_PER_CONTRACT
    collateral = None if example.collateral is None else example.collateral * SHARES_PER_CONTRACT
    roc = None if credit is None or not collateral or collateral <= 0 else credit / collateral
    no_collateral = (
        _gap(example.edge_id, "the template's collateral is not computed for this position")
        if collateral is None
        else None
    )
    chance, chance_unknown = _chance(example, day)
    return PremiumOption(
        example.edge_id, example.underlying_id, legs, min(x.expiry for x in legs), credit,
        collateral, roc, chance, None, chance_unknown, no_collateral,
    )  # fmt: skip


def load_premium_options(
    ctx: ReadContext, setups: Mapping[str, QualifyingSetup], picks: Sequence[tuple[str, str]]
) -> dict[str, PremiumOption]:
    """The row of each ``(setup id, instrument id)`` of ``picks`` (the Premium ideas shown, under
    their best setup), by instrument id: one example read per setup."""
    docs = {e.id: e for e in parsed_edges(ctx, ctx.user.user_id)}
    wanted: dict[str, list[str]] = {}
    for setup_id, iid in picks:
        wanted.setdefault(setup_id, []).append(iid)
    out: dict[str, PremiumOption] = {}
    for setup_id, iids in wanted.items():
        doc = docs.get(setup_id)
        if doc is None:
            why = f"{setup_id}'s document is not readable at {ctx.session.date}"
            out.update({i: PremiumOption(setup_id, i, unknown=_gap(setup_id, why)) for i in iids})
            continue
        examples = load_option_examples(ctx, setups[setup_id].edge, doc.outcome, iids)
        out.update({e.underlying_id: premium_option(e, ctx.session.date) for e in examples})
    return out
