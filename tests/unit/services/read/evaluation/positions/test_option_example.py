"""The example position of an option pick (ADR 0088 2.8, decision 19), over a fixture chain since
no site setup declares an option template yet: the legs the harness's own selector chooses at S,
the credit and collateral, the declared exits as dollar marks, the exit session, and every missing
part UNKNOWN with its reason (no chain, no price, no legs, case values not applied yet)."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from algotrade.config.edges.positions.cases import Case, CaseValue
from algotrade.config.edges.positions.spec import PositionSpec
from algotrade.config.edges.positions.templates import OPTION, Leg
from algotrade.core.model.predicates import Group
from algotrade.features.rollups.options.wing_search import select_legs
from algotrade.features.rollups.positioning.chain_inputs import one_row_per_contract
from algotrade.services.read.evaluation.positions import option_example as module
from algotrade.services.read.evaluation.positions.exit_rule import (
    ExitRule,
    Stop,
    StopBasis,
    StopKind,
)
from algotrade.services.read.evaluation.positions.option_example import load_option_examples
from algotrade.services.read.values import UnknownCode

S = date(2026, 10, 30)
SPY = "EQ:SPY"
EDGE: Any = SimpleNamespace(id="put_write")
CTX: Any = SimpleNamespace(session=SimpleNamespace(date=S))
SHORT_PUT = (Leg(OPTION, -1, "P", "delta", delta=0.30),)


def _outcome(**changes: Any) -> Any:
    spec = PositionSpec("short_put", legs=SHORT_PUT, collateral="cash_secured", **changes)
    return SimpleNamespace(position=spec, tenor_days=30, start_offset_sessions=1)


def _chain() -> pd.DataFrame:
    """SPY at 500: puts 440..500 on the 20 Nov and 18 Dec expiries, two-sided quotes."""
    rows = []
    for expiry in (date(2026, 11, 20), date(2026, 12, 18)):
        for strike in range(440, 505, 10):
            mid = max(0.4, (strike - 440) * 0.25 + (0.5 if expiry.month == 12 else 0.0))
            rows.append({
                "instrument_id": f"OPT:SPY{expiry:%y%m%d}P{strike}", "underlying_id": SPY,
                "expiry": expiry, "right": "P", "strike": float(strike), "bid": mid - 0.05,
                "ask": mid + 0.05, "open_interest": 1000.0, "volume": 50.0, "iv": 0.18,
                "theta": -0.05,
            })  # fmt: skip
    return pd.DataFrame(rows)


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    rule: ExitRule,
    chain: pd.DataFrame | None = None,
    status: str = "OK",
    spot: float | None = 500.0,
) -> list[date | None]:
    chain = _chain() if chain is None else chain
    asked: list[date | None] = []

    def exit_rule_at(ctx: Any, edge: Any, *, bounded: bool, **kw: Any) -> ExitRule:
        asked.append(kw.get("expiry"))
        return rule

    monkeypatch.setattr(module, "exit_rule_at", exit_rule_at)
    monkeypatch.setattr(module, "load_chain_quotes", lambda ctx, ids: chain)
    monkeypatch.setattr(
        module, "load_chains", lambda ctx, ids: {i: SimpleNamespace(status=status) for i in ids}
    )
    monkeypatch.setattr(module, "load_chain_spots", lambda ctx, ids: dict.fromkeys(ids, spot))
    return asked


def test_the_legs_are_the_harnesss_selection_with_credit_collateral_and_declared_marks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    declared = Stop(StopKind.DECLARED, fraction=2.0, basis=StopBasis.CREDIT)
    rule = ExitRule("put_write", declared, 15, take_profit=0.5, exit_dte=21)
    asked = _wire(monkeypatch, rule)
    (ex,) = load_option_examples(CTX, EDGE, _outcome(), [SPY])
    entry = date(2026, 11, 2)  # the close one session after Friday's S
    expected = select_legs(
        _chain(), SHORT_PUT, 500.0, S, 30, "monthly", not_before=module._advance(entry, 15)
    )
    assert [leg.instrument_id for leg in ex.legs] == [c.instrument_id for c in expected.legs]
    (leg,) = ex.legs
    assert leg.qty == -1 and leg.right == "P" and leg.iv == 0.18 and leg.open_interest == 1000.0
    assert ex.net_credit == pytest.approx(leg.mid)  # one sold put: the credit is its mid
    assert ex.collateral == pytest.approx(leg.strike)  # cash secured: the strike per share
    assert ex.stop_debit == pytest.approx(leg.mid * 3.0)  # a loss of 2x the credit
    assert ex.take_profit_debit == pytest.approx(leg.mid * 0.5)
    assert leg.expiry == date(2026, 12, 18)  # 20 Nov is before entry + hold: refused
    assert ex.exit_dte_date == date(2026, 11, 27)  # 21 days before 18 Dec, a session
    assert ex.entry_session == entry
    assert ex.exit_session == min(module._advance(entry, 15), leg.expiry)
    assert ex.share_entry_close is None  # no share leg
    assert ex.chain_asof == S and ex.unknown is None
    assert asked == [None, leg.expiry]  # the hold cap, then the rule given the selected expiry


def test_a_history_stop_is_a_loss_on_the_collateral(monkeypatch: pytest.MonkeyPatch) -> None:
    history = Stop(StopKind.HISTORY, fraction=0.04, winners=60, basis=StopBasis.COLLATERAL)
    _wire(monkeypatch, ExitRule("put_write", history, 15))
    (ex,) = load_option_examples(CTX, EDGE, _outcome(), [SPY])
    assert ex.stop_debit is None and ex.collateral is not None
    assert ex.stop_loss == pytest.approx(0.04 * ex.collateral)


@pytest.mark.parametrize(
    ("status", "spot", "chain", "code"),
    [
        ("NO_CHAIN", 500.0, None, UnknownCode.NO_ROW),
        ("OK", None, None, UnknownCode.NO_ROW),
        ("OK", 500.0, _chain().assign(bid=0.0), UnknownCode.NOT_APPLICABLE),  # no two-sided quote
    ],
)
def test_no_chain_no_price_or_no_legs_is_unknown_with_its_reason(
    monkeypatch: pytest.MonkeyPatch, status: str, spot: float | None, chain: Any, code: str
) -> None:
    _wire(monkeypatch, ExitRule("put_write", None, 15), chain, status, spot)
    (ex,) = load_option_examples(CTX, EDGE, _outcome(), [SPY])
    assert ex.legs == () and ex.unknown is not None and ex.unknown.code == code


def test_case_valued_parameters_are_unknown_until_a_run_applies_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = _wire(monkeypatch, ExitRule("put_write", None, 15))
    case = CaseValue("tenor_days", (Case(Group("all", ()), 45),), 30)
    (ex,) = load_option_examples(CTX, EDGE, _outcome(cases=(case,)), [SPY])
    assert ex.unknown is not None and "E13b" in str(ex.unknown.cause) and asked == []


def test_no_hold_and_no_picks(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire(monkeypatch, ExitRule("put_write", None, None))
    (ex,) = load_option_examples(CTX, EDGE, _outcome(), [SPY])
    assert ex.unknown is not None and ex.unknown.code == UnknownCode.NOT_RUN
    assert load_option_examples(CTX, EDGE, _outcome(), []) == ()


def test_the_expiry_floor_counts_the_hold_from_the_entry_not_s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hold that reaches past the November expiry from the entry takes December's, as the
    harness's window end (entry + hold) refuses an earlier expiry."""
    _wire(monkeypatch, ExitRule("put_write", None, 15))
    (ex,) = load_option_examples(CTX, EDGE, _outcome(), [SPY])
    floor = module._advance(date(2026, 11, 2), 15)
    assert all(leg.expiry >= floor for leg in ex.legs) and ex.legs


def test_duplicate_quotes_of_a_contract_keep_the_latest_row() -> None:
    rows = pd.DataFrame(
        {"instrument_id": ["A", "A"], "ts": ["2026-10-30T19:00Z", "2026-10-30T20:00Z"],
         "bid": [1.0, 2.0]}
    )  # fmt: skip
    assert list(one_row_per_contract(rows)["bid"]) == [2.0]
