"""A cycle's state (X7, the wheel): a put, then covered calls after assignment until called away;
the cycle sums to premium - strike + the last share price (the money identity), the gap between
the phases is booked once, an assignment is learned after the close (the next phase enters the
session after), and a missing row or spot ends the cycle (never filled)."""

from datetime import date, timedelta

import pytest

from algotrade.services.evaluation.cross_section.portfolio.cycle import (
    NO_ROW,
    NO_SPOT,
    CycleRow,
    chain,
    stock_share,
)

P = [date(2026, 1, 20), date(2026, 2, 18), date(2026, 3, 19), date(2026, 4, 20)]
ONE = timedelta(days=1)
K = 100.0
CAP = K * 100


def later(day: date) -> date:
    return day + ONE


def _put(i: int, assigned: bool, *, late: bool = False, last: float = 98.0) -> CycleRow:
    # per-contract dollars; assigned: the intrinsic loss (K - last) is in the option leg
    pnl = 100 * (2.0 - max(K - last, 0.0)) if assigned else 200.0
    return CycleRow(P[i] + (ONE if late else 0 * ONE), P[i + 1], pnl, 0.0, assigned, CAP, 101.0,
                    last)  # fmt: skip


def _call(i: int, assigned: bool, *, entry: float, last: float, late: bool = True) -> CycleRow:
    stock = 100 * (last - entry)
    option = 150.0 - (100 * max(last - 105.0, 0.0) if assigned else 0.0)
    return CycleRow(
        P[i] + (ONE if late else 0 * ONE),
        P[i + 1],
        option + stock,
        stock,
        assigned,
        0.0,
        entry,
        last,
        100.0,
    )


def always(entry: date) -> bool:
    return True


def keyed(*rows: CycleRow | None) -> dict[date, CycleRow | None]:
    return {r.entry: r for r in rows if r is not None}


def test_an_expired_put_enters_the_next_put_at_the_placement_itself() -> None:
    puts = keyed(_put(0, False), _put(1, False))
    trades, lost = chain({"put": puts}, P[:2], later, always)
    assert [t.phase for t in trades] == ["put", "put"]
    assert trades[0].value == pytest.approx(200 / CAP)
    assert not lost


def test_assignment_hands_the_shares_to_a_call_the_next_session_and_called_away_ends_it() -> None:
    # put assigned at 95 (strike 100): -5/share intrinsic, +2 premium; shares gap 95 -> 96
    puts = keyed(_put(0, True, last=95.0), _put(2, False, late=True))  # the put after a call-away
    calls = keyed(_call(1, True, entry=96.0, last=107.0))
    trades, lost = chain({"put": puts, "call": calls}, P[:3], later, always)
    assert [t.phase for t in trades] == ["put", "call", "put"]
    assert trades[2].entry == P[2] + ONE  # the put waits a session after the call-away
    assert not lost
    cycle = sum(t.value for t in trades[:2]) * CAP
    # premium - strike + called-away price: 2 + 1.5 - 100 + 105 per share (cap at the call strike)
    assert cycle == pytest.approx(100 * (2.0 + 1.5 + 105.0 - K))


def test_a_call_that_expires_is_followed_by_another_call() -> None:
    puts = keyed(_put(0, True, last=95.0))
    calls = keyed(
        _call(1, False, entry=96.0, last=97.0), _call(2, True, entry=97.0, last=110.0, late=False)
    )
    trades, _ = chain({"put": puts, "call": calls}, P[:3], later, always)
    assert [t.phase for t in trades] == ["put", "call", "call"]


def test_the_gap_is_booked_once_to_the_call_phase() -> None:
    puts = keyed(_put(0, True, last=95.0))
    calls = keyed(_call(1, False, entry=93.0, last=93.0))
    trades, _ = chain({"put": puts, "call": calls}, P[:2], later, always)
    assert trades[0].stock == 0.0  # the put's loss is its option leg
    assert trades[1].stock * CAP == pytest.approx(100 * (93.0 - 95.0))  # the gap only


def test_a_missing_row_ends_the_cycle_into_cash_then_a_fresh_put() -> None:
    puts = keyed(_put(0, True), _put(2, False))
    trades, lost = chain({"put": puts}, P[:3], later, always)  # no call row at P[1] + 1
    assert [t.phase for t in trades] == ["put", "put"]
    assert lost[NO_ROW] == 1


def test_a_missing_spot_ends_the_cycle_never_guessing_the_gap() -> None:
    put = _put(0, True)
    blind = CycleRow(put.entry, put.exit, put.pnl, 0.0, True, CAP, 101.0, None)
    calls = keyed(_call(1, False, entry=96.0, last=97.0))
    trades, lost = chain({"put": keyed(blind), "call": calls}, P[:2], later, always)
    assert len(trades) == 1
    assert lost[NO_SPOT] == 1


def test_stock_share_of_the_return() -> None:
    puts = keyed(_put(0, True, last=95.0))
    calls = keyed(_call(1, True, entry=96.0, last=107.0))
    trades, _ = chain({"put": puts, "call": calls}, P[:2], later, always)
    shown = stock_share(trades)
    assert shown["stock_return"] + shown["option_return"] == pytest.approx(
        sum(t.value for t in trades)
    )
    assert stock_share(())["stock_share"] is None


def test_a_closed_gate_keeps_a_new_cycle_out_but_never_cuts_one_in_progress() -> None:
    puts = keyed(_put(0, False), _put(1, False))
    trades, lost = chain({"put": puts}, P[:2], later, lambda entry: entry != P[0])
    assert [t.entry for t in trades] == [P[1]] and not lost  # the closed session is cash
    puts = keyed(_put(0, True, last=95.0))
    calls = keyed(_call(1, False, entry=96.0, last=97.0))
    trades, _ = chain({"put": puts, "call": calls}, P[:2], later, lambda entry: entry == P[0])
    assert [t.phase for t in trades] == ["put", "call"]  # the gate shut after the put opened


def test_an_unknown_gate_is_counted_as_a_gap_not_read_as_closed() -> None:
    trades, lost = chain({"put": keyed(_put(0, False))}, P[:1], later, lambda entry: None)
    assert not trades and lost["gate_unknown"] == 1
