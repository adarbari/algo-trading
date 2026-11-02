"""Roll a sold option (ownership ``option-calculators``; plan V11, screen OptRoll): the contract
a trader sold (right, strike, expiry, and optionally the price it was sold at), what buying it
back costs tonight at the mid, and the rolls to a later expiry at the same strike or one further
out of the money, each with its extra credit, new breakeven, credit per extra day and our delta.

- **Rolls**: the next ``MAX_EXPIRIES`` listed expiries after the contract's, within
  ``MAX_DAYS`` of the session; at each, the strike sold and up to ``STRIKES_EACH - 1`` listed
  strikes further out of the money (a put's lower, a call's higher) within ``STRIKE_RANGE`` of
  it, each with a two-sided quote. ``same_delta`` keeps instead, per expiry, the one strike
  whose |delta| is nearest the sold contract's.
- **Extra credit**: the new contract's mid less the buy-back mid; a roll that costs money (not
  positive) is left out unless ``include_debits``.
- **New breakeven**: ``payoff.short_breakeven`` over the price sold at plus the extra credit;
  None when the trader did not give the price sold at (the screen asks for it).

Gaps are ``Unknown``: the name cannot be priced (``session_inputs``), or the sold contract is
not listed tonight with a two-sided quote (NOT_APPLICABLE / ILLIQUID), or the rolls at
the same delta are asked for and the sold contract has no delta of ours
(NOT_APPLICABLE). Nothing is stored.
"""

import math
from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.data.chains import OPTION_QUOTES
from algotrade.features.rollups.premium.band_pick import OurDeltas
from algotrade.quant.options import payoff
from algotrade.services.preview.options.pool import (
    CALL,
    RIGHT_CODE,
    figures,
    listed_expiries,
    priced_pool,
    underlying,
)
from algotrade.services.read.context import ReadContext
from algotrade.services.read.options.session_inputs import (
    PricingInputs,
    gap,
    load_session_inputs,
    report_inside,
)
from algotrade.services.read.values import Unknown, UnknownCode

__all__ = ["Contract", "Roll", "RollPreview", "preview_roll"]

MAX_EXPIRIES = 6  # later expiries offered
MAX_DAYS = 120  # calendar days from the session
STRIKES_EACH = 3  # strikes per expiry: the one sold and the next ones out of the money
STRIKE_RANGE = 0.10  # how far from the sold strike a further strike may be
_MATCH = 1e-6  # a typed strike matches a listed one within this


@dataclass(frozen=True)
class Contract:
    """A sold option as the trader typed it: ``right`` put or call, its strike and expiry."""

    right: str
    strike: float
    expiry: date


@dataclass(frozen=True)
class Roll:
    """Buying the sold contract back and selling ``strike`` at ``expiry``, per share."""

    expiry: date
    strike: float
    extra_credit: float
    new_breakeven: float | None
    credit_per_extra_day: float
    delta: float
    report_inside: bool | None
    report_inside_unknown: Unknown | None


@dataclass(frozen=True)
class RollPreview:
    """The sold contract tonight (``buy_back`` its mid, ``delta`` ours, ``above_strike`` the
    underlying's price over the strike less one, ``days_left`` to its expiry, ``over_collected``
    the buy-back less the price sold at, None when not given) and its ``rolls`` in expiry
    order, the nearest strike first."""

    underlying_id: str
    session: date
    priced_at: float
    contract: Contract
    sold_at: float | None
    buy_back: float
    over_collected: float | None
    above_strike: float
    days_left: int
    delta: float
    rolls: tuple[Roll, ...]


def _further(right: str, sold: float, strike: float) -> bool:
    """``strike`` is the sold one or further out of the money, within ``STRIKE_RANGE``."""
    if right == CALL:
        return sold - _MATCH <= strike <= sold * (1 + STRIKE_RANGE) + _MATCH
    return sold * (1 - STRIKE_RANGE) - _MATCH <= strike <= sold + _MATCH


def _candidates(pool: pd.DataFrame, contract: Contract, delta: float, same: bool) -> pd.DataFrame:
    if pool.empty:
        return pool
    if same:
        gaps = (pool["delta"].abs() - abs(delta)).abs().dropna()
        return pool.iloc[0:0] if gaps.empty else pool.loc[[gaps.idxmin()]]
    near = pool[[_further(contract.right, contract.strike, k) for k in pool["strike"]]]
    order = (near["strike"] - contract.strike).abs().sort_values(kind="stable").index
    return near.loc[order[:STRIKES_EACH]]


def _rolls(
    inputs: PricingInputs,
    deltas: OurDeltas,
    session: date,
    contract: Contract,
    buy_back: float,
    delta: float,
    sold_at: float | None,
    include_debits: bool,
    same_delta: bool,
) -> tuple[Roll, ...]:
    later = [
        e
        for e in listed_expiries(inputs, contract.right, session)
        if e > contract.expiry and (e - session).days <= MAX_DAYS
    ][:MAX_EXPIRIES]
    out: list[Roll] = []
    for expiry in later:
        pool = priced_pool(inputs, deltas, session, expiry, contract.right)
        inside = report_inside(session, expiry, inputs.report)
        for strike, mid, new_delta in figures(_candidates(pool, contract, delta, same_delta)):
            credit = mid - buy_back
            if credit <= 0 and not include_debits:
                continue
            total = None if sold_at is None else sold_at + credit
            breakeven = (
                None
                if total is None
                else float(payoff.short_breakeven(strike, total, contract.right))
            )
            extra_days = (expiry - contract.expiry).days
            out.append(
                Roll(
                    expiry=expiry,
                    strike=strike,
                    extra_credit=credit,
                    new_breakeven=breakeven,
                    credit_per_extra_day=float(payoff.credit_per_day(credit, extra_days)),
                    delta=new_delta,
                    report_inside=None if isinstance(inside, Unknown) else inside,
                    report_inside_unknown=inside if isinstance(inside, Unknown) else None,
                )
            )
    return tuple(out)


def preview_roll(
    ctx: ReadContext,
    key: str,
    contract: Contract,
    sold_at: float | None = None,
    include_debits: bool = False,
    same_delta: bool = False,
) -> RollPreview | Unknown:
    """The rolls of ``contract`` on the instrument ``key`` names for ``ctx.session``, or why
    there are none to show."""
    underlying_id = underlying(ctx, key)
    found = load_session_inputs(ctx, underlying_id)
    if isinstance(found, Unknown):
        return found
    inputs, _ = found
    session = ctx.session.date
    what = f"{underlying_id} {contract.right} {contract.strike:g} expiring {contract.expiry}"
    if contract.expiry <= session:
        why = f"{what}: the expiry is not after {session}"
        return gap(ctx, UnknownCode.NOT_APPLICABLE, "EXPIRED", why, OPTION_QUOTES)
    deltas = OurDeltas(inputs.curve, inputs.q)
    pool = priced_pool(inputs, deltas, session, contract.expiry, contract.right)
    sold = pool[(pool["strike"] - contract.strike).abs() <= _MATCH]
    if sold.empty:
        chain = inputs.chain
        listed = chain[
            (chain["right"] == RIGHT_CODE[contract.right])
            & (chain["expiry"] == contract.expiry)
            & ((chain["strike"] - contract.strike).abs() <= _MATCH)
        ]
        code, status = (
            (UnknownCode.ILLIQUID, "ILLIQUID")
            if not listed.empty
            else (UnknownCode.NOT_APPLICABLE, "NOT_LISTED")
        )
        why = f"{what}: {status.lower().replace('_', ' ')} on {session}"
        return gap(ctx, code, status, why, OPTION_QUOTES)
    buy_back, delta = float(sold["mid"].iloc[0]), float(sold["delta"].iloc[0])
    if same_delta and not math.isfinite(delta):  # no vol inverts: no delta to match
        why = f"{what}: no delta of ours on {session} to roll to"
        return gap(ctx, UnknownCode.NOT_APPLICABLE, "NO_DELTA", why, OPTION_QUOTES)
    rolls = _rolls(
        inputs, deltas, session, contract, buy_back, delta, sold_at, include_debits, same_delta
    )
    return RollPreview(
        underlying_id=underlying_id,
        session=session,
        priced_at=inputs.spot,
        contract=contract,
        sold_at=sold_at,
        buy_back=buy_back,
        over_collected=None if sold_at is None else buy_back - sold_at,
        above_strike=inputs.spot / contract.strike - 1,
        days_left=(contract.expiry - session).days,
        delta=delta,
        rolls=rolls,
    )
