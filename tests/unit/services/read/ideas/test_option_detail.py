"""``load_idea_option``: an option pick's sections (plan O4): the example's legs as derived
figures (no bid or ask), the most you can lose, theta, the chance in the money, the one-sigma
day, the calendar flags, a missing input UNKNOWN with its reason and never a zero, and the
premium floor UNKNOWN until a setup declares a minimum credit."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from algotrade.config.edges.positions.templates import OPTION, SHARES, Leg
from algotrade.services.read.evaluation.positions.option_example import OptionExample, OptionLeg
from algotrade.services.read.ideas import option_detail as module
from algotrade.services.read.ideas.option_detail import load_idea_option
from algotrade.services.read.values import Unknown, UnknownCode

S = date(2026, 10, 30)
EXPIRY = date(2026, 12, 4)
EDGE: Any = SimpleNamespace(id="put_write")
CTX: Any = SimpleNamespace(session=SimpleNamespace(date=S), user=SimpleNamespace(user_id="u"))
IID = "EQ:KTLX"


def _leg(right: str = "P", strike: float = 55.0, qty: int = -1, **kw: Any) -> OptionLeg:
    found: dict[str, Any] = {
        "bid": 0.66, "ask": 0.76, "mid": 0.71, "delta": -0.2, "iv": 0.4, "theta": -0.02,
        "open_interest": 900.0, "volume": 40.0,
    }  # fmt: skip
    found.update(kw)
    return OptionLeg(
        f"OPT:{right}{strike}", right, strike, EXPIRY, qty, found["bid"], found["ask"],
        found["mid"], found["delta"], found["iv"], found["theta"], found["open_interest"],
        found["volume"],
    )  # fmt: skip


def _example(legs: tuple[OptionLeg, ...] | None = None, **kw: Any) -> OptionExample:
    base: dict[str, Any] = {
        "legs": (_leg(),) if legs is None else legs, "spot": 58.9,
        "entry_session": date(2026, 11, 2), "net_credit": 0.71, "collateral": 55.0,
        "exit_session": EXPIRY, "stop_debit": None, "take_profit_debit": 0.355,
    }  # fmt: skip
    base.update(kw)
    return OptionExample(EDGE.id, IID, S, **base)


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    example: OptionExample,
    legs: tuple[Leg, ...] = (Leg(OPTION, -1, "P", "delta", delta=0.2),),
    next_ex: Any = date(2027, 1, 20),
    report: date | None = date(2026, 12, 3),
) -> None:
    spec = SimpleNamespace(legs=legs)
    doc = SimpleNamespace(id=EDGE.id, outcome=SimpleNamespace(position=spec))
    monkeypatch.setattr(module, "parsed_edges", lambda ctx, user: [doc])
    monkeypatch.setattr(module, "load_option_examples", lambda ctx, e, o, u: (example,))
    ahead = () if report is None else (SimpleNamespace(kind="own_earnings", date=report),)
    events = SimpleNamespace(gaps=(), ahead=ahead)
    monkeypatch.setattr(module, "load_instrument_events", lambda ctx, ids, days: {IID: events})
    info = SimpleNamespace(name=module.NEXT_EX_DATE)
    cell = SimpleNamespace(
        value=None if next_ex is None else next_ex.isoformat(),
        unknown=None if next_ex is not None else Unknown(UnknownCode.NO_ROW, None),
        info=info,
    )
    monkeypatch.setattr(module, "load_feature_values", lambda ctx, ids, names: {IID: (cell,)})


def test_a_short_put_gets_derived_figures_and_no_bid_or_ask(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch, _example())
    out = load_idea_option(CTX, EDGE, IID)
    assert out.unknown is None
    (leg,) = out.legs
    assert not hasattr(leg, "bid") and not hasattr(leg, "ask")
    assert (leg.right, leg.strike, leg.qty, leg.mid) == ("put", 55.0, -1, 0.71)
    assert leg.p_itm is not None and 0.0 < leg.p_itm < 0.5
    assert out.net_credit == 0.71 and out.cash_set_aside == pytest.approx(5500.0)
    assert out.max_loss == pytest.approx((55 - 0.71) * 100) and not out.unbounded
    assert out.theta_per_day == pytest.approx(2.0)
    assert out.one_sigma_loss is not None and out.one_sigma_loss > 0
    assert out.risk_unknown is None


def test_the_calendar_flags_say_when_the_name_reports_or_goes_ex_dividend_before_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch, _example(), next_ex=date(2026, 11, 20), report=date(2026, 12, 3))
    out = load_idea_option(CTX, EDGE, IID)
    assert (out.report_in_life, out.report_date) == (True, date(2026, 12, 3))
    assert (out.ex_div_before_expiry, out.ex_div_date) == (True, date(2026, 11, 20))
    _wire(monkeypatch, _example(), next_ex=date(2027, 1, 20), report=None)
    clear = load_idea_option(CTX, EDGE, IID)
    assert (clear.report_in_life, clear.ex_div_before_expiry) == (False, False)


def test_an_ex_dividend_date_not_stored_is_unknown_not_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch, _example(), next_ex=None)
    out = load_idea_option(CTX, EDGE, IID)
    assert out.ex_div_before_expiry is None and out.calendar_unknown is not None


def test_a_naked_call_is_unbounded_and_has_no_max_loss(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire(monkeypatch, _example((_leg("C", 65.0),)), legs=(Leg(OPTION, -1, "C", "delta"),))
    out = load_idea_option(CTX, EDGE, IID)
    assert out.max_loss is None and out.unbounded


def test_a_covered_call_loses_the_share_cost_less_the_credit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    example = _example((_leg("C", 65.0),), share_entry_close=58.9)
    _wire(monkeypatch, example, legs=(Leg(SHARES, 100), Leg(OPTION, -1, "C", "delta")))
    out = load_idea_option(CTX, EDGE, IID)
    assert out.max_loss == pytest.approx((58.9 - 0.71) * 100) and not out.unbounded


def test_a_leg_without_an_iv_or_theta_is_unknown_with_a_reason_never_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch, _example((_leg(iv=None, theta=None),)))
    out = load_idea_option(CTX, EDGE, IID)
    assert out.theta_per_day is None and out.one_sigma_loss is None
    assert out.legs[0].p_itm is None
    assert out.risk_unknown is not None and out.max_loss is not None


def test_a_pick_with_no_example_is_unknown_with_its_reason_and_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    why = Unknown(UnknownCode.NO_ROW, None)
    _wire(monkeypatch, OptionExample(EDGE.id, IID, S, unknown=why))
    out = load_idea_option(CTX, EDGE, IID)
    assert out.unknown is why and out.legs == () and out.max_loss is None
    assert out.floor_unknown is None


def test_a_setup_without_an_option_position_is_not_applicable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc = SimpleNamespace(id=EDGE.id, outcome=SimpleNamespace(position=None))
    monkeypatch.setattr(module, "parsed_edges", lambda ctx, user: [doc])
    out = load_idea_option(CTX, EDGE, IID)
    assert out.unknown is not None and out.unknown.code is UnknownCode.NOT_APPLICABLE


def test_the_monday_floor_is_unknown_until_a_setup_declares_a_minimum_credit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch, _example())
    out = load_idea_option(CTX, EDGE, IID)
    assert out.monday_floor is None
    assert out.floor_unknown is not None
    assert out.floor_unknown.code is UnknownCode.NOT_APPLICABLE


def test_a_zero_credit_is_a_credit_and_a_missing_one_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch, _example(net_credit=0.0))
    zero = load_idea_option(CTX, EDGE, IID)
    assert zero.max_loss == pytest.approx(55 * 100) and zero.risk_unknown is None
    _wire(monkeypatch, _example(net_credit=None))
    none = load_idea_option(CTX, EDGE, IID)
    assert none.max_loss is None and not none.unbounded and none.risk_unknown is not None


def test_an_ex_dividend_before_the_entry_or_a_report_before_it_is_not_in_life(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch, _example(), next_ex=date(2026, 10, 30), report=date(2026, 10, 30))
    out = load_idea_option(CTX, EDGE, IID)
    assert out.ex_div_before_expiry is False and out.report_in_life is False
