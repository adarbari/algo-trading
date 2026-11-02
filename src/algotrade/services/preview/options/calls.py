"""Calls on shares a trader holds (ownership ``option-calculators``; plan V11, screen OptCalls):
from the shares held and the trader's price for them (after premiums already collected), the
calls they could sell tonight at the mid, and the coming dividend that decides early exercise.

- **Expiries**: the listed ones nearest ``TARGET_DAYS`` (``band_pick.bucket_expiries``, the
  grid's rule: within 30% of each target, distinct).
- **Strikes**: at each expiry, the two-sided calls from ``LOW`` x the lower of the price and the
  trader's price up to ``HIGH`` x the price, the ``STRIKES_EACH`` nearest the price kept, in
  strike order. A strike below the trader's price is flagged (``below_price``): being called
  there locks in a loss.
- **Figures** per share: the premium (mid), the premium over the trader's price, the return if
  called away (``payoff.called_away_return``), the report inside the expiry, the ex-dividend date
  on or before the expiry (None: no ex-date known yet, the source lists one about 30 days ahead)
  and the early-exercise risk: in the money with an extrinsic value (``payoff.extrinsic``) below
  the dividend, when one is known before the expiry.
- **Contracts** are whole hundreds of the shares typed; the total premium is per contract x 100.
- **Dividend**: the next ex-date and amount by catalogue name (``dividend_schedule@v1``) and the
  session one must own the shares by at the close (the session before the ex-date); UNKNOWN when
  none is announced.

Gaps are ``Unknown`` (``session_inputs``). Nothing is stored.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.core.time.calendar import previous_session
from algotrade.features.rollups.premium.band_pick import OurDeltas, bucket_expiries
from algotrade.quant.options import payoff
from algotrade.services.preview.options.pool import CALL, figures, listed_expiries, priced_pool
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.features import FeatureValue
from algotrade.services.read.options.session_inputs import (
    load_session_inputs,
    report_inside,
)
from algotrade.services.read.values import Unknown

__all__ = ["CallRow", "CallsPreview", "Dividend", "preview_calls"]

NEXT_EX_DATE = "rollup.dividend_schedule@v1.next_ex_date"
NEXT_DIV_AMOUNT = "rollup.dividend_schedule@v1.next_div_amount"
TARGET_DAYS = (14, 30, 45)
STRIKES_EACH = 6
LOW, HIGH = 0.95, 1.10
CONTRACT_SIZE = 100


@dataclass(frozen=True)
class Dividend:
    """The next dividend: its ex-date, cash amount per share and the session to own the shares
    by at the close to collect it."""

    ex_date: date
    amount: float
    own_by: date


@dataclass(frozen=True)
class CallRow:
    """Selling the call at ``strike`` expiring ``expiry``, per share."""

    expiry: date
    days: int
    strike: float
    premium: float
    premium_over_price: float
    if_called: float
    below_price: bool
    report_inside: bool | None
    report_inside_unknown: Unknown | None
    ex_div_before_expiry: bool | None
    early_exercise_risk: bool | None


@dataclass(frozen=True)
class CallsPreview:
    """The calls on ``shares`` held at ``price`` (``above_price``: the underlying's close over
    it less one); ``contracts`` whole hundreds, ``rows`` by expiry then strike, ``premium_total``
    of each row for every contract (None when under 100 shares) in the rows' order."""

    underlying_id: str
    session: date
    priced_at: float
    shares: int
    price: float
    contracts: int
    above_price: float
    rows: tuple[CallRow, ...]
    premium_total: tuple[float | None, ...]
    dividend: Dividend | Unknown


def _dividend(ex_date: FeatureValue, amount: FeatureValue) -> Dividend | Unknown:
    """The next dividend, or why it is not known (``value`` is None exactly when ``unknown``
    says why)."""
    for value in (ex_date, amount):
        if value.unknown is not None:
            return value.unknown
    day = date.fromisoformat(str(ex_date.value))
    return Dividend(day, float(amount.value), previous_session(day))  # type: ignore[arg-type]


def _strikes(pool: pd.DataFrame, spot: float, price: float) -> pd.DataFrame:
    """The strikes offered at one expiry (see the module docstring)."""
    near = pool[(pool["strike"] >= LOW * min(spot, price)) & (pool["strike"] <= HIGH * spot)]
    order = (near["strike"] - spot).abs().sort_values(kind="stable").index[:STRIKES_EACH]
    return near.loc[order].sort_values("strike")


def _early(
    dividend: Dividend | Unknown, expiry: date, mid: float, spot: float, strike: float
) -> tuple[bool | None, bool | None]:
    """(the ex-date is on or before ``expiry``, an early exercise is likely); both None when no
    dividend is known."""
    if isinstance(dividend, Unknown):
        return None, None
    before = dividend.ex_date <= expiry
    in_money = strike < spot
    risk = (
        before and in_money and float(payoff.extrinsic(mid, spot, strike, CALL)) < dividend.amount
    )
    return before, risk


def preview_calls(
    ctx: ReadContext, underlying_id: str, shares: int, price: float
) -> CallsPreview | Unknown:
    """The calls ``shares`` of ``underlying_id`` held at ``price`` could be sold against, for
    ``ctx.session``, or why there are none to show."""
    found = load_session_inputs(ctx, underlying_id, (NEXT_EX_DATE, NEXT_DIV_AMOUNT))
    if isinstance(found, Unknown):
        return found
    inputs, (ex_date, amount) = found
    session, spot = ctx.session.date, inputs.spot
    dividend = _dividend(ex_date, amount)
    deltas = OurDeltas(inputs.curve, inputs.q)
    contracts = shares // CONTRACT_SIZE
    rows: list[CallRow] = []
    for bucket in bucket_expiries(listed_expiries(inputs, CALL, session), session, TARGET_DAYS):
        if bucket.expiry is None:
            continue
        expiry = bucket.expiry
        pool = priced_pool(inputs, deltas, session, expiry, CALL)
        inside = report_inside(session, expiry, inputs.report)
        for strike, mid, _ in figures(_strikes(pool, spot, price)):
            before, risk = _early(dividend, expiry, mid, spot, strike)
            rows.append(
                CallRow(
                    expiry=expiry,
                    days=(expiry - session).days,
                    strike=strike,
                    premium=mid,
                    premium_over_price=mid / price,
                    if_called=float(payoff.called_away_return(strike, mid, price)),
                    below_price=strike < price,
                    report_inside=None if isinstance(inside, Unknown) else inside,
                    report_inside_unknown=inside if isinstance(inside, Unknown) else None,
                    ex_div_before_expiry=before,
                    early_exercise_risk=risk,
                )
            )
    totals = tuple(r.premium * CONTRACT_SIZE * contracts if contracts else None for r in rows)
    return CallsPreview(
        underlying_id=underlying_id,
        session=session,
        priced_at=spot,
        shares=shares,
        price=price,
        contracts=contracts,
        above_price=spot / price - 1,
        rows=tuple(rows),
        premium_total=totals,
        dividend=dividend,
    )
