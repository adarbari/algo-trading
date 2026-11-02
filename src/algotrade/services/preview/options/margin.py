"""Buying power for a sold option (ownership ``option-calculators``; plan V11, screen OptMargin):
from a contract a trader picks and a count, what it ties up, never how much to trade (ADR 0083:
no position size, no stored account profile).

- **Cash-secured**: a put's strike x 100 per contract; a call's shares at tonight's price x 100
  (a covered call holds the shares, and needs no option margin beyond them).
- **Margin account**: the exchange minimum for an UNCOVERED short option (for a call, a naked
  call: a different position from the covered call above) (Reg-T, the Cboe rule
  most US brokers start from; owner-away decision 2026-11-02, docs/decisions/log.md: no named
  broker's rule), per share: the mid plus the larger of 20% of the underlying's price less the
  out-of-the-money amount, and 10% of the strike (a put) or of the underlying's price (a call);
  x 100 per contract. A broker may require more. A broker rule is a rule, not maths, so it
  lives here and not in ``quant/``.
- **Premium**: the mid x 100 x contracts, and its share of what each account holds, for the
  calendar days to expiry.
- **Size against trading**: the contracts over the day's volume and over the open interest at
  that strike (None where either is not positive or missing).
- **Stress**: a put only: what it would be in the money, on every contract and before the
  premium, if the underlying fell as far as it did in its worst stored reference episode
  (``episode_behaviour@v1``'s ``dd_<episode>``, by catalogue name); UNKNOWN when none is stored.

Gaps are ``Unknown`` (``session_inputs``, a contract not listed or one-sided). Nothing is stored.
"""

import math
from dataclasses import dataclass
from datetime import date

from algotrade.features.rollups.premium.band_pick import OurDeltas
from algotrade.features.rollups.price import episodes
from algotrade.services.preview.options.pool import CALL, Contract, listed_contract, underlying
from algotrade.services.read.availability.cause import feature_cause
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.features import FeatureValue
from algotrade.services.read.options.session_inputs import load_session_inputs
from algotrade.services.read.values import Unknown, UnknownCode

__all__ = ["REG_T", "MarginPreview", "Stress", "preview_margin", "reg_t_per_share"]

CONTRACT_SIZE = 100
REG_T = "reg_t"  # the one rule offered (decision 2026-11-02)
EPISODES = tuple(e.key for e in episodes.EPISODES)  # episode_behaviour@v1's dd_<episode>
_DRAWDOWN = "rollup.episode_behaviour@v1.dd_{}"


@dataclass(frozen=True)
class Stress:
    """The underlying's worst stored episode fall (``drop``, negative) and what the put would be
    in the money then, on every contract, before the premium (``in_the_money``)."""

    episode: str
    drop: float
    in_the_money: float


@dataclass(frozen=True)
class MarginPreview:
    """What ``contracts`` of ``contract`` tie up under ``rule``, in dollars."""

    underlying_id: str
    session: date
    priced_at: float
    contract: Contract
    contracts: int
    rule: str
    days: int
    premium: float
    premium_total: float
    cash_secured: float
    margin_held: float
    premium_over_cash: float
    premium_over_margin: float
    volume_share: float | None
    open_interest_share: float | None
    stress: Stress | Unknown | None


def reg_t_per_share(right: str, spot: float, strike: float, mid: float) -> float:
    """The exchange minimum per share for an uncovered short ``right`` (see the docstring)."""
    if right == CALL:
        out_of_money = max(strike - spot, 0.0)
        return mid + max(0.20 * spot - out_of_money, 0.10 * spot)
    out_of_money = max(spot - strike, 0.0)
    return mid + max(0.20 * spot - out_of_money, 0.10 * strike)


def _share(contracts: int, of: float | None) -> float | None:
    """``contracts`` over ``of``; None where ``of`` is missing or not positive."""
    if of is None or not math.isfinite(of) or of <= 0:
        return None
    return contracts / of


def _stress(
    session: date, contract: Contract, spot: float, contracts: int, drops: tuple[FeatureValue, ...]
) -> Stress | Unknown | None:
    """The put's stress over the worst stored episode; None for a call."""
    if contract.right == CALL:
        return None
    known = [
        (float(v.value), episode)
        for episode, v in zip(EPISODES, drops, strict=True)
        if v.unknown is None and isinstance(v.value, int | float) and math.isfinite(v.value)
    ]
    if not known:
        names = ", ".join(_DRAWDOWN.format(e) for e in EPISODES)
        cause = feature_cause(names, "no episode drawdown stored", "NULL", session)
        return Unknown(UnknownCode.NULL, cause)
    drop, episode = min(known)
    low = spot * (1 + drop)
    itm = max(contract.strike - low, 0.0) * CONTRACT_SIZE * contracts
    return Stress(episode, drop, itm)


def preview_margin(
    ctx: ReadContext, key: str, contract: Contract, contracts: int
) -> MarginPreview | Unknown:
    """What ``contracts`` of ``contract`` on the instrument ``key`` names tie up for
    ``ctx.session``, or why it cannot be worked out."""
    underlying_id = underlying(ctx, key)
    asked = tuple(_DRAWDOWN.format(e) for e in EPISODES)
    found = load_session_inputs(ctx, underlying_id, asked)
    if isinstance(found, Unknown):
        return found
    inputs, drops = found
    session, spot = ctx.session.date, inputs.spot
    sold = listed_contract(ctx, inputs, OurDeltas(inputs.curve, inputs.q), contract)
    if isinstance(sold, Unknown):
        return sold
    mid = sold.mid
    per_contract = CONTRACT_SIZE * contracts
    collateral = contract.strike if contract.right != CALL else spot
    cash = collateral * per_contract
    held = reg_t_per_share(contract.right, spot, contract.strike, mid) * per_contract
    total = mid * per_contract
    return MarginPreview(
        underlying_id=underlying_id,
        session=session,
        priced_at=spot,
        contract=contract,
        contracts=contracts,
        rule=REG_T,
        days=(contract.expiry - session).days,
        premium=mid,
        premium_total=total,
        cash_secured=cash,
        margin_held=held,
        premium_over_cash=total / cash,
        premium_over_margin=total / held,
        volume_share=_share(contracts, sold.volume),
        open_interest_share=_share(contracts, sold.open_interest),
        stress=_stress(session, contract, spot, contracts, drops),
    )
