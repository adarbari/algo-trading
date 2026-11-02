"""The option row of a Premium idea (O3): derived figures of the example position at the session
(credit and collateral per contract, their ratio, the chance a sold leg is assigned), and every
missing part an ``Unknown``, never a zero."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from algotrade.quant.options.position import p_itm
from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.evaluation.positions.option_example import OptionExample, OptionLeg
from algotrade.services.read.ideas import premium as module
from algotrade.services.read.ideas.premium import load_premium_options, premium_option
from algotrade.services.read.values import Unknown, UnknownCode

S = date(2026, 11, 2)
EXPIRY = date(2026, 12, 2)


def leg(right: str = "P", strike: float = 95.0, qty: int = -1, iv: float | None = 0.3) -> OptionLeg:
    return OptionLeg(
        f"OPT:{right}{strike}", right, strike, EXPIRY, qty, 1.1, 1.3, 1.2, -0.3, iv, None, 500,
        20,
    )  # fmt: skip


def example(*legs: OptionLeg, collateral: float | None = 95.0, **changes: Any) -> OptionExample:
    base = OptionExample(
        "put_sell", "EQ:A", S, legs, spot=100.0, net_credit=1.2, collateral=collateral
    )
    return OptionExample(**{**base.__dict__, **changes})


def test_a_short_put_gives_its_figures_per_contract() -> None:
    row = premium_option(example(leg()), S)
    assert (row.credit, row.collateral) == pytest.approx((120.0, 9500.0))
    assert row.return_on_collateral == pytest.approx(120.0 / 9500.0)
    days = np.array([float((EXPIRY - S).days)])
    expected = float(p_itm(100.0, np.array([95.0]), np.array([0.3]), days, np.array([False]))[0])
    assert row.assignment_chance == pytest.approx(expected)
    assert row.expiry == EXPIRY and row.legs[0].mid == 1.2 and row.unknown is None


def test_no_example_is_unknown_with_its_reason_and_no_figure() -> None:
    gap = Unknown(UnknownCode.NO_ROW, run_cause("put_sell", "no usable chain"))
    row = premium_option(example(unknown=gap), S)
    assert row.unknown is gap and row.credit is None and row.assignment_chance is None


def test_a_sold_leg_without_a_stored_iv_has_no_chance_only_that_figure_unknown() -> None:
    row = premium_option(example(leg(iv=None)), S)
    assert row.assignment_chance is None and row.chance_unknown is not None
    assert row.credit == pytest.approx(120.0)


def test_no_collateral_is_unknown_never_a_zero_return() -> None:
    row = premium_option(example(leg(), collateral=None), S)
    assert row.collateral is None and row.return_on_collateral is None
    assert row.collateral_unknown is not None


def test_a_long_wing_is_never_counted_as_assignable() -> None:
    lone = premium_option(example(leg()), S).assignment_chance
    winged = premium_option(example(leg(), leg(strike=90.0, qty=1)), S).assignment_chance
    assert winged == lone


def test_rows_are_read_per_setup_and_a_missing_document_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, tuple[str, ...]]] = []

    def examples(ctx: Any, edge: Any, outcome: Any, iids: Any) -> tuple[OptionExample, ...]:
        calls.append((edge.id, tuple(iids)))
        return tuple(example(leg(), underlying_id=i) for i in iids)

    monkeypatch.setattr(
        module, "parsed_edges", lambda ctx, user: [SimpleNamespace(id="a", outcome=None)]
    )
    monkeypatch.setattr(module, "load_option_examples", examples)
    ctx: Any = SimpleNamespace(session=SimpleNamespace(date=S), user=SimpleNamespace(user_id="me"))
    setups: Any = {"a": SimpleNamespace(edge=SimpleNamespace(id="a")), "b": None}
    found = load_premium_options(ctx, setups, [("a", "EQ:A"), ("a", "EQ:B"), ("b", "EQ:C")])
    assert calls == [("a", ("EQ:A", "EQ:B"))]
    assert found["EQ:B"].credit == pytest.approx(120.0)
    assert found["EQ:C"].unknown is not None and found["EQ:C"].credit is None
