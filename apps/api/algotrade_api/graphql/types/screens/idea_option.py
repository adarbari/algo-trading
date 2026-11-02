"""``IdeaOption``: the option sections of an idea page (plan O4): the example position as derived
figures (no bid or ask), the declared exits as dollar marks, the most you can lose per contract,
the position's theta, chance in the money and one-sigma day, the report and ex-dividend flags and
the premium floor. Decided on the server (services/read/ideas/option_detail.py); a part with a
missing input carries its own `unknown`."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read import values
from algotrade.services.read.ideas import option_detail
from algotrade_api.graphql.types.evaluation.exit_rule import ExitRule
from algotrade_api.graphql.types.instruments.feature import Unknown


@strawberry.type(
    description="One leg of the example position: `qty` signed (negative: sold), `mid` and our "
    "`delta` per share, `pItm` the quoted chance it finishes in the money (not backtested)"
)
class OptionLegView:
    right: str
    strike: float
    expiry: dt.date
    qty: int
    mid: float
    delta: float | None
    p_itm: float | None

    @classmethod
    def of(cls, d: option_detail.OptionLegView) -> Self:
        return cls(
            right=d.right,
            strike=d.strike,
            expiry=d.expiry,
            qty=d.qty,
            mid=d.mid,
            delta=d.delta,
            p_itm=d.p_itm,
        )


@strawberry.type(
    description="An option pick's sections, amounts in dollars per contract and prices per "
    "share: the example `legs`, `netCredit` and `cashSetAside`, the setup's `exitRule` with "
    "the marks on the credit, `maxLoss` (null and `unbounded` when a naked call has no limit), "
    "`thetaPerDay`, `oneSigmaLoss`, the report and ex-dividend flags and `mondayFloor`; each "
    "group's `unknown` says why a part is missing"
)
class IdeaOption:
    chain_date: dt.date
    unknown: Unknown | None
    legs: list[OptionLegView]
    chain_close: float | None
    entry_session: dt.date | None
    exit_session: dt.date | None
    net_credit: float | None
    cash_set_aside: float | None
    exit_rule: ExitRule | None
    stop_debit: float | None
    stop_loss: float | None
    take_profit_debit: float | None
    exit_dte_date: dt.date | None
    max_loss: float | None
    unbounded: bool
    theta_per_day: float | None
    one_sigma_loss: float | None
    risk_unknown: Unknown | None
    report_in_life: bool | None
    report_date: dt.date | None
    ex_dividend_in_life: bool | None
    ex_div_date: dt.date | None
    calendar_unknown: Unknown | None
    monday_floor: float | None
    floor_unknown: Unknown | None

    @classmethod
    def of(cls, d: option_detail.IdeaOption) -> Self:
        def one(u: values.Unknown | None) -> Unknown | None:
            return Unknown.of(u) if u is not None else None

        return cls(
            chain_date=d.chain_date,
            unknown=one(d.unknown),
            legs=[OptionLegView.of(leg) for leg in d.legs],
            chain_close=d.chain_close,
            entry_session=d.entry_session,
            exit_session=d.exit_session,
            net_credit=d.net_credit,
            cash_set_aside=d.cash_set_aside,
            exit_rule=ExitRule.of(d.exit_rule) if d.exit_rule is not None else None,
            stop_debit=d.stop_debit,
            stop_loss=d.stop_loss,
            take_profit_debit=d.take_profit_debit,
            exit_dte_date=d.exit_dte_date,
            max_loss=d.max_loss,
            unbounded=d.unbounded,
            theta_per_day=d.theta_per_day,
            one_sigma_loss=d.one_sigma_loss,
            risk_unknown=one(d.risk_unknown),
            report_in_life=d.report_in_life,
            report_date=d.report_date,
            ex_dividend_in_life=d.ex_dividend_in_life,
            ex_div_date=d.ex_div_date,
            calendar_unknown=one(d.calendar_unknown),
            monday_floor=d.monday_floor,
            floor_unknown=one(d.floor_unknown),
        )
