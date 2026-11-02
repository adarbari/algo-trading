"""The wheel's book (X7) over stored rows: the row held to its expiry is the one that counts
(chosen from its legs and window, never from how it ended), an assigned put hands its shares to the
call, the shares' move over the gap and the call's own is the stock return, and a call row that is
missing breaks the cycle into cash, by hand."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from algotrade.config.edges.positions.key import position_key, wheel_call, with_legs
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.evaluation.time_series.wheel import wheel_book
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.schemas import STRUCTURE_PNL
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped, structure_pnl_row
from tests.unit.config.edges.test_named import WHEEL, sleeve
from tests.unit.services.evaluation.time_series.conftest import AS_OF, KNOWN, SPY_ID
from tests.unit.services.evaluation.time_series.test_sleeve import TEMPLATES

S = [date(2024, 1, 22), date(2024, 2, 20), date(2024, 3, 18)]
E = [date(2024, 2, 16), date(2024, 3, 15)]  # the expiries the first two rows are held to
HOLDS = (18, 19, 24)
STRIKE = 100.0


def edge() -> Any:
    held = sleeve(**WHEEL)
    return with_legs(held, TEMPLATES)


def _row(outcome: Any, hold: int, day: date, **fields: Any) -> dict[str, Any]:
    return structure_pnl_row(
        SPY_ID, position_key(outcome, hold), day, hold=hold,
        ts=datetime.combine(day, datetime.min.time(), UTC), price_source="option_history",
        licence="personal", **{"collateral": STRIKE, "entry_spot": 100.0, **fields},
    )  # fmt: skip


def world(drop_call: bool = False) -> StoreReader:
    wheel_edge = edge()
    put = wheel_edge.outcome
    call = wheel_call(put, TEMPLATES)
    assert call is not None
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    after = [
        d + timedelta(days=1) for d in S
    ]  # the session after each placement (after an assignment)
    rows: dict[date, list[dict[str, Any]]] = {d: [] for d in [*S, *after]}
    other = replace(put, strike_delta=0.35)  # another setup's put on the same name and session
    rows[S[0]].append(
        _row(other, 18, S[0], window_end=E[0], exit_session=E[0], leg_expiries=[E[0]],
             exit_kind="EXPIRED", exit_basis="INTRINSIC", pnl_mid=99.0, spot_path=[100.0, 101.0])
    )  # fmt: skip
    # S0: the put held 18 sessions ends on its expiry E0 and is assigned (spot 95, strike 100); the
    # 19-session one is a decoy that outlives the expiry and ends by quote
    rows[S[0]] += [
        _row(put, 18, S[0], window_end=E[0], exit_session=E[0], leg_expiries=[E[0]],
             exit_kind="ASSIGNED", exit_basis="INTRINSIC", pnl_mid=-3.0, option_pnl=-3.0,
             spot_path=[100.0, 95.0]),
        _row(put, 19, S[0], window_end=E[0] + timedelta(days=1), exit_session=E[0],
             leg_expiries=[E[0]], exit_kind="HORIZON", pnl_mid=2.0, spot_path=[100.0, 95.0]),
    ]  # fmt: skip
    # S1: the covered call entered with the shares at 94 (the gap from 95 is -1), called away at
    # 107 over its 105 strike: shares +13, option 1.5 - 2 = -0.5
    if not drop_call:
        rows[after[1]].append(
            _row(call, 18, after[1], window_end=E[1], exit_session=E[1], leg_expiries=[E[1], E[1]],
                 leg_kinds=["option", "shares"], leg_qty=[-1.0, 100.0],
                 leg_contract_ids=["OPT:C", None], leg_rights=["C", None],
                 leg_strikes=[105.0, None], leg_entry_mid=[1.5, 94.0],
                 leg_entry_half_spread=[0.05, 0.0], leg_entry_delta=[0.3, 1.0],
                 entry_spot=94.0, exit_kind="ASSIGNED", exit_basis="INTRINSIC", pnl_mid=12.5,
                 option_pnl=-0.5, stock_pnl=13.0, spot_path=[94.0, 107.0])
        )  # fmt: skip
    # the put after the call-away enters the session after the placement and expires worthless
    for day in (S[2], after[2]):  # a fresh put after a break, or after a call-away
        end = day + timedelta(days=26)
        rows[day].append(
            _row(put, 18, day, window_end=end, exit_session=end, leg_expiries=[end],
                 exit_kind="EXPIRED", exit_basis="INTRINSIC", pnl_mid=2.0, option_pnl=2.0,
                 spot_path=[100.0, 101.0])
        )  # fmt: skip
    for day, frame in rows.items():
        if not frame:
            continue
        writer.write_table(STRUCTURE_PNL, day, f"c-{day}", stamped(frame, day, f"c-{day}", KNOWN))
    return StoreReader(backend)


def open_gate(entry: date) -> bool:
    return True


def book(reader: StoreReader) -> dict[str, Any]:
    return wheel_book(reader, edge(), TEMPLATES, {"SPY": SPY_ID}, 1, S, open_gate, AS_OF)


def test_the_stock_return_is_the_gap_and_the_calls_own_share_move() -> None:
    figures = book(world())
    assert figures["cohorts"] == 3 and figures["lost"] == 0
    assert figures["stock_return"] == pytest.approx((13.0 - 1.0) / STRIKE)  # +13 shares, -1 gap
    assert figures["option_return"] < 0.0  # the put's -3 and the call's -0.5, over the put's 2.0


def test_another_positions_row_on_the_same_session_is_never_the_phases_trade() -> None:
    figures = book(world())
    assert figures["option_return"] < 0.0  # the 99.0 decoy of another key would make it a win


def test_the_hold_that_ends_on_the_expiry_is_the_row_that_counts_not_the_decoy() -> None:
    # the decoy (pnl +2.0, HORIZON) would make the put phase a win: the assigned row's -3 counts
    first = book(world())
    assert first["option_return"] < 0.0


def test_a_missing_call_row_breaks_the_cycle_into_cash_then_a_fresh_put() -> None:
    figures = book(world(drop_call=True))
    assert figures["lost"] == 1  # the call phase, never filled
    assert figures["cohorts"] == 2  # the first put and the fresh put
    assert figures["stock_return"] == 0.0


def test_a_book_of_a_sleeve_that_is_no_wheel_is_refused() -> None:
    plain = with_legs(sleeve(), TEMPLATES)
    with pytest.raises(ConfigurationError, match="not a wheel"):
        wheel_book(world(), plain, TEMPLATES, {"SPY": SPY_ID}, 1, S, open_gate, AS_OF)
