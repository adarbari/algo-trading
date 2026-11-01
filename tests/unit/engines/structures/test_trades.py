"""The trades of a window (ADR 0088, design 2.4, 2.4a, 2.5) on synthetic chains priced by
Black-Scholes: legs chosen from S's chain alone, the hold cap, an exit rule acting at its own close
(a trade that exits at k is priced from closes S..k only), a catalogue-field rule acting a close
later, an UNKNOWN rule never firing and counted, expiry at intrinsic, collateral by rule, a stock
leg's part of the P&L, and a name UNMEASURED with a reason when a session lacks its chain."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from algotrade.config.edges.positions.spec import ExitRule
from algotrade.config.edges.positions.templates import Leg
from algotrade.core.model.predicates import Group, Rule
from algotrade.data.chains import OK_LABEL
from algotrade.engines.structures.chain import DayChain
from algotrade.engines.structures.trades import collateral_of, select_window, walk_trades
from algotrade.features.rollups.options.wing_search import ChosenLeg, LegSelection
from algotrade.quant.black_scholes import price

DAYS = [date(2026, 10, 5) + timedelta(days=i) for i in range(5)]  # S .. T (calendar days here)
EXPIRY = date(2026, 11, 20)
VOL, HALF = 0.30, 0.05
A, B = "EQ:A", "EQ:B"
SHORT_PUT = Leg("option", -1, "P", "delta", 0.30)
WING = Leg("option", 1, "P", "delta", 0.10)
STOCK = Leg("shares", 100)
CALL = Leg("option", -1, "C", "delta", 0.30)


def quotes(name: str, day: date, spot: float, expiry: date = EXPIRY) -> pd.DataFrame:
    rows = []
    for strike in range(70, 135, 5):
        for right in ("C", "P"):
            mid = float(price(spot, strike, (expiry - day).days / 365, 0.0, 0.0, VOL, right == "C"))
            rows.append({"instrument_id": f"{name}:{right}{strike}", "underlying_id": name,
                         "expiry": expiry, "right": right, "strike": float(strike),
                         "bid": max(mid - HALF, 0.01), "ask": mid + HALF,
                         "open_interest": 100 + strike})  # fmt: skip
    return pd.DataFrame(rows)


def window(
    spots: list[float], names: tuple[str, ...] = (A,), expiry: date = EXPIRY,
    missing: dict[int, set[str]] | None = None,
) -> list[DayChain]:  # fmt: skip
    days = []
    for i, day in enumerate(DAYS[: len(spots)]):
        gone = (missing or {}).get(i, set())
        here = [n for n in names if n not in gone]
        options = pd.concat([quotes(n, day, spots[i], expiry) for n in here], ignore_index=True)
        days.append(DayChain(day, options, dict.fromkeys(here, spots[i]),
                             dict.fromkeys(here, OK_LABEL), None))  # fmt: skip
    return days


def run(
    days: list[DayChain],
    legs: list[Leg],
    collateral: str = "cash_secured",
    rules: tuple[ExitRule, ...] = (),
    catalogue: list[dict] | None = None,
    tenor: int = 21,
    **kw: object,
):
    selected = select_window(days[0], legs, tenor, "any", days[-1].day)
    empty = [{} for _ in days[1:]]
    return walk_trades(days, legs, collateral, selected, list(rules), catalogue or empty, **kw)


def rule(kind: str, field: str, op: str, value: float) -> ExitRule:
    return ExitRule(kind, Group("all", (Rule(field, op, value),)))


def test_a_trade_held_to_the_cap_is_priced_from_the_chains_with_its_legs_and_greeks() -> None:
    days = window([100.0, 101.0, 102.0, 101.0, 103.0])
    (trade,) = run(days, [SHORT_PUT])
    strike = trade.strikes[0]
    assert trade.reason is None and trade.exit_kind == "HORIZON" and trade.exit_basis == "QUOTE"
    assert trade.exit_index == 4 and trade.exit_session == DAYS[4]
    entry = float(price(100.0, strike, (EXPIRY - DAYS[0]).days / 365, 0.0, 0.0, VOL, False))
    final = float(price(103.0, strike, (EXPIRY - DAYS[4]).days / 365, 0.0, 0.0, VOL, False))
    assert trade.entry_net_mid == pytest.approx(-entry)
    assert trade.exit_net_mid == pytest.approx(-final)
    assert trade.pnl_mid == pytest.approx(entry - final) == pytest.approx(trade.option_pnl)
    assert trade.stock_pnl == 0.0 and trade.collateral == strike
    assert trade.entry_half_spread == pytest.approx(HALF)
    assert trade.exit_half_spread == pytest.approx(HALF)
    assert trade.leg_delta[0] == pytest.approx(-0.30, abs=0.06) and trade.delta > 0  # short put
    assert trade.gamma < 0 and trade.vega < 0 and trade.theta > 0
    assert trade.entry_oi_min == 100 + strike and np.isfinite(trade.pnl_hedged_mid)
    assert trade.realised_vol > 0 and trade.max_adverse >= 0 and trade.path_min <= trade.pnl_mid


def test_a_position_exit_acts_at_its_own_close_and_is_priced_from_closes_to_it_only() -> None:
    # the put loses value as the stock rises: take profit once 5% of the credit is captured
    days = window([100.0, 104.0, 90.0, 90.0, 90.0])
    take = rule("TAKE_PROFIT", "position.profit_share_of_credit", "gte", 0.05)
    (trade,) = run(days, [SHORT_PUT], rules=(take,))
    assert trade.exit_kind == "TAKE_PROFIT" and trade.exit_index == 1
    assert trade.exit_session == DAYS[1] and trade.pnl_mid > 0
    later = days[:1] + [days[1]] + [DayChain(DAYS[2], None, {}, {}, None)] * 3  # chains gone
    (same,) = run(later, [SHORT_PUT], rules=(take,))
    assert same.pnl_mid == pytest.approx(trade.pnl_mid) and same.reason is None  # never read


def test_a_catalogue_rule_acts_a_close_after_it_is_observed_and_unknown_never_fires() -> None:
    days = window([100.0, 100.0, 100.0, 100.0, 100.0])
    cond = rule("CONDITION", "market.stress", "gt", 1.0)
    seen = [{A: {"market.stress": 2.0}}, {A: {"market.stress": 0.0}}, {}, {}]
    (trade,) = run(days, [SHORT_PUT], rules=(cond,), catalogue=seen)
    assert trade.exit_kind == "CONDITION" and trade.exit_index == 2  # observed at 1, acts at 2
    unknown = [{}, {}, {}, {}]  # no stored field for any close: never fires, counted
    (never,) = run(days, [SHORT_PUT], rules=(cond,), catalogue=unknown)
    assert never.exit_kind == "HORIZON" and never.unknown_closes == 3


def test_a_leg_expiring_at_the_cap_is_valued_at_intrinsic_and_settled() -> None:
    expiry = DAYS[-1]
    days = window([100.0, 99.0, 98.0, 97.0, 90.0], expiry=expiry)
    (itm,) = run(days, [SHORT_PUT], tenor=1)
    assert itm.exit_basis == "INTRINSIC" and itm.exit_kind in ("ASSIGNED", "EXPIRED")
    strike = itm.strikes[0]
    assert itm.exit_net_mid == pytest.approx(-max(strike - 90.0, 0.0))
    otm = window([100.0, 100.0, 100.0, 100.0, 110.0], expiry=expiry)
    (win,) = run(otm, [SHORT_PUT], tenor=1)
    assert win.exit_kind == "EXPIRED" and win.expired_otm is True and win.exit_net_mid == 0.0
    assert win.exit_half_spread == 0.0  # no spread is paid at expiry


def test_a_name_with_no_chain_at_the_cap_is_unmeasured_but_an_earlier_exit_is_not() -> None:
    days = window([100.0, 104.0, 100.0, 100.0, 100.0], names=(A, B), missing={4: {B}})
    take = rule("TAKE_PROFIT", "position.profit_share_of_credit", "gte", 0.05)
    held, exited = run(days, [SHORT_PUT]), run(days, [SHORT_PUT], rules=(take,))
    by_name = {t.name: t for t in held}
    assert by_name[A].reason is None
    assert by_name[B].reason == f"NO_CHAIN:{DAYS[4]}" and by_name[B].pnl_mid != by_name[B].pnl_mid
    assert {t.name: t.reason for t in exited} == {A: None, B: None}  # B left after its exit


def test_a_chain_with_no_expiry_far_enough_is_a_reason_not_a_trade() -> None:
    days = window([100.0, 100.0, 100.0], expiry=DAYS[1])  # nothing expires on or after T (day 2)
    (trade,) = run(days, [SHORT_PUT])
    assert trade.reason == "NO_EXPIRY" and trade.exit_session is None and trade.kinds == []


def test_a_stock_leg_adds_its_pnl_per_share_and_the_collateral_is_the_notional() -> None:
    days = window([100.0, 101.0, 102.0, 103.0, 104.0])
    (trade,) = run(days, [STOCK, CALL], collateral="notional")
    assert trade.kinds == ["shares", "option"] and trade.qty == [100.0, -1.0]
    assert trade.stock_pnl == pytest.approx(4.0) and trade.collateral == pytest.approx(100.0)
    assert trade.pnl_mid == pytest.approx(trade.stock_pnl + trade.option_pnl)
    assert trade.contract_ids[0] is None and trade.leg_delta[0] == 1.0
    assert trade.delta == pytest.approx(1.0 + (-1) * trade.leg_delta[1])  # shares + short call


def chosen(leg: Leg, strike: float) -> ChosenLeg:
    return ChosenLeg(leg, f"OPT:{strike}", strike, EXPIRY, 1.0, -0.3)


def test_collateral_is_cash_secured_max_loss_or_not_computed() -> None:
    put_spread = LegSelection((chosen(SHORT_PUT, 100.0), chosen(WING, 95.0)))
    legs = [SHORT_PUT, WING]
    assert collateral_of("cash_secured", legs, put_spread, 100.0, -1.2) == 100.0
    assert collateral_of("max_loss", legs, put_spread, 100.0, -1.2) == pytest.approx(5.0 - 1.2)
    naked_call = LegSelection((chosen(CALL, 105.0),))
    assert np.isnan(collateral_of("max_loss", [CALL], naked_call, 100.0, -1.0))  # unbounded
    assert np.isnan(collateral_of("regt", legs, put_spread, 100.0, -1.2))  # not in this slice
    assert np.isnan(collateral_of("cash_secured", [CALL], naked_call, 100.0, -1.0))  # no short put
    assert np.isnan(collateral_of("notional", [SHORT_PUT], put_spread, 100.0, -1.2))  # no stock leg


def test_a_missing_interior_mark_leaves_the_lowest_pnl_unknown_not_the_min_of_the_rest() -> None:
    days = window([100.0, 101.0, 102.0, 103.0, 104.0], names=(A, B), missing={2: {A}})
    trade = {t.name: t for t in run(days, [SHORT_PUT])}[A]
    assert trade.reason is None and np.isfinite(trade.pnl_mid)  # the trade itself is measured
    assert np.isnan(trade.path_min)


def test_a_position_with_a_stock_leg_stores_no_max_adverse_until_the_stock_is_in_it() -> None:
    days = window([100.0, 101.0, 102.0, 103.0, 104.0])
    (trade,) = run(days, [STOCK, CALL], collateral="notional")
    assert np.isnan(trade.max_adverse)
    (plain,) = run(days, [SHORT_PUT])
    assert np.isfinite(plain.max_adverse)
