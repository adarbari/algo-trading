"""``POST /preview/options/{roll,calls,margin}``: the option calculators (plan V11) over figures a
trader types, priced on the request's session. Derived figures only: no bid, ask, last or size
field anywhere (``tests/architecture/options/test_trader_option_figures.py``). A gap is served in
public words (its kind and Guide term); its cause chain is an admin's only (ADR 0056: marked
``ADMIN_CAUSE``, the routes ``redact``)."""

import math
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from algotrade.services.preview.options import calls, margin, roll
from algotrade.services.read.availability.cause import ADMIN_CAUSE
from algotrade.services.read.values import Unknown
from algotrade_api.schemas.availability import CauseLink
from algotrade_api.schemas.health import Schema

Right = Literal["put", "call"]


class OptionGap(Schema):
    """Why a figure or a whole preview is not available, in public words (ADR 0056)."""

    code: str
    kind: str
    guide_term: str
    kind_text: str
    cause: list[CauseLink] | None = Field(
        description="the chain behind it, root cause first (admins only: null for anyone else)",
        json_schema_extra={ADMIN_CAUSE: None},
    )


def gap_of(found: Unknown | None) -> OptionGap | None:
    """``found`` as served (``redact`` strips the cause for anyone but an admin); None for
    None."""
    if found is None:
        return None
    return OptionGap(
        code=found.code.value,
        kind=found.kind.value,
        guide_term=found.guide_term,
        kind_text=found.public_reason,
        cause=[CauseLink.model_validate(link) for link in found.cause.links],
    )


class RollBody(BaseModel):
    key: str = Field(description="the underlying: a ticker or an instrument id")
    right: Right = Field("put", description="the right of the option sold")
    strike: float = Field(gt=0, description="the strike of the option sold")
    expiry: date = Field(description="the expiry of the option sold")
    sold_at: float | None = Field(
        None, ge=0, description="the price per share it was sold at (for the new breakeven)"
    )
    include_debits: bool = Field(False, description="also show rolls that cost money")
    same_delta: bool = Field(False, description="per expiry, only the strike nearest its delta")


class RollRow(Schema):
    expiry: date
    strike: float
    extra_credit: float
    new_breakeven: float | None
    credit_per_extra_day: float | None
    delta: float | None
    report_inside: bool | None
    report_inside_unknown: OptionGap | None


class RollPreview(Schema):
    underlying_id: str
    session: date
    priced_at: float
    right: Right
    strike: float
    expiry: date
    sold_at: float | None
    buy_back: float
    over_collected: float | None
    above_strike: float
    days_left: int
    delta: float | None
    rolls: list[RollRow]


class RollResult(Schema):
    preview: RollPreview | None = Field(description="the rolls (None: see gap)")
    gap: OptionGap | None = Field(description="why there is no preview (None: there is one)")


class CallsBody(BaseModel):
    key: str = Field(description="the underlying: a ticker or an instrument id")
    shares: int = Field(gt=0, le=10_000_000, description="shares held")
    price: float = Field(gt=0, description="the trader's price per share, after premiums")


class CallRow(Schema):
    expiry: date
    days: int
    strike: float
    premium: float
    premium_over_price: float
    if_called: float | None
    below_price: bool
    report_inside: bool | None
    report_inside_unknown: OptionGap | None
    ex_div_before_expiry: bool | None
    early_exercise_risk: bool | None
    premium_total: float | None


class Dividend(Schema):
    ex_date: date
    amount: float
    own_by: date


class CallsPreview(Schema):
    underlying_id: str
    session: date
    priced_at: float
    shares: int
    price: float
    contracts: int
    above_price: float
    rows: list[CallRow]
    dividend: Dividend | None
    dividend_unknown: OptionGap | None


class CallsResult(Schema):
    preview: CallsPreview | None = Field(description="the calls (None: see gap)")
    gap: OptionGap | None = Field(description="why there is no preview (None: there is one)")


def _finite(value: float) -> float | None:
    """``value``, or None where it is NaN (a figure that is not defined)."""
    return None if math.isnan(value) else value


def roll_result(found: roll.RollPreview | Unknown) -> RollResult:
    """The roll preview as served."""
    if isinstance(found, Unknown):
        return RollResult(preview=None, gap=gap_of(found))
    rows = [
        RollRow(
            expiry=r.expiry,
            strike=r.strike,
            extra_credit=r.extra_credit,
            new_breakeven=r.new_breakeven,
            credit_per_extra_day=_finite(r.credit_per_extra_day),
            delta=_finite(r.delta),
            report_inside=r.report_inside,
            report_inside_unknown=gap_of(r.report_inside_unknown),
        )
        for r in found.rolls
    ]
    preview = RollPreview(
        underlying_id=found.underlying_id,
        session=found.session,
        priced_at=found.priced_at,
        right=found.contract.right,  # type: ignore[arg-type]
        strike=found.contract.strike,
        expiry=found.contract.expiry,
        sold_at=found.sold_at,
        buy_back=found.buy_back,
        over_collected=found.over_collected,
        above_strike=found.above_strike,
        days_left=found.days_left,
        delta=_finite(found.delta),
        rolls=rows,
    )
    return RollResult(preview=preview, gap=None)


def calls_result(found: calls.CallsPreview | Unknown) -> CallsResult:
    """The calls preview as served."""
    if isinstance(found, Unknown):
        return CallsResult(preview=None, gap=gap_of(found))
    rows = [
        CallRow(
            expiry=r.expiry,
            days=r.days,
            strike=r.strike,
            premium=r.premium,
            premium_over_price=r.premium_over_price,
            if_called=_finite(r.if_called),
            below_price=r.below_price,
            report_inside=r.report_inside,
            report_inside_unknown=gap_of(r.report_inside_unknown),
            ex_div_before_expiry=r.ex_div_before_expiry,
            early_exercise_risk=r.early_exercise_risk,
            premium_total=total,
        )
        for r, total in zip(found.rows, found.premium_total, strict=True)
    ]
    known = not isinstance(found.dividend, Unknown)
    preview = CallsPreview(
        underlying_id=found.underlying_id,
        session=found.session,
        priced_at=found.priced_at,
        shares=found.shares,
        price=found.price,
        contracts=found.contracts,
        above_price=found.above_price,
        rows=rows,
        dividend=Dividend.model_validate(found.dividend) if known else None,
        dividend_unknown=None if known else gap_of(found.dividend),  # type: ignore[arg-type]
    )
    return CallsResult(preview=preview, gap=None)


class MarginBody(BaseModel):
    key: str = Field(description="the underlying: a ticker or an instrument id")
    right: Right = Field("put", description="the right of the option")
    strike: float = Field(gt=0, description="its strike")
    expiry: date = Field(description="its expiry")
    contracts: int = Field(gt=0, le=100_000, description="how many contracts")


class Stress(Schema):
    episode: str
    drop: float
    in_the_money: float


class MarginPreview(Schema):
    underlying_id: str
    session: date
    priced_at: float
    right: Right
    strike: float
    expiry: date
    contracts: int
    rule: str = Field(description="the margin rule applied: reg_t, the exchange minimum")
    days: int
    premium: float
    premium_total: float
    cash_secured: float = Field(
        description="a put's strike, a call's shares at tonight's price (covered), x 100 x n"
    )
    margin_held: float = Field(
        description="the exchange minimum for an uncovered short option (a call: a naked call)"
    )
    premium_over_cash: float
    premium_over_margin: float = Field(description="the premium over the uncovered minimum")
    volume_share: float | None
    open_interest_share: float | None
    stress: Stress | None
    stress_unknown: OptionGap | None


class MarginResult(Schema):
    preview: MarginPreview | None = Field(description="what it ties up (None: see gap)")
    gap: OptionGap | None = Field(description="why there is no preview (None: there is one)")


def margin_result(found: margin.MarginPreview | Unknown) -> MarginResult:
    """The buying-power preview as served."""
    if isinstance(found, Unknown):
        return MarginResult(preview=None, gap=gap_of(found))
    stress = found.stress
    preview = MarginPreview(
        underlying_id=found.underlying_id,
        session=found.session,
        priced_at=found.priced_at,
        right=found.contract.right,  # type: ignore[arg-type]
        strike=found.contract.strike,
        expiry=found.contract.expiry,
        contracts=found.contracts,
        rule=found.rule,
        days=found.days,
        premium=found.premium,
        premium_total=found.premium_total,
        cash_secured=found.cash_secured,
        margin_held=found.margin_held,
        premium_over_cash=found.premium_over_cash,
        premium_over_margin=found.premium_over_margin,
        volume_share=found.volume_share,
        open_interest_share=found.open_interest_share,
        stress=Stress.model_validate(stress) if isinstance(stress, margin.Stress) else None,
        stress_unknown=gap_of(stress) if isinstance(stress, Unknown) else None,
    )
    return MarginResult(preview=preview, gap=None)
