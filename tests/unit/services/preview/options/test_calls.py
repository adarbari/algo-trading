"""Calls on shares held, on exactly the session's chain: expiries by the grid's bucket rule,
strikes around the price, below-your-price flagged, the return if called away, the dividend
that decides early exercise (UNKNOWN when none is announced, never "no dividend"), whole
contracts, derived figures only and every UNKNOWN case."""

import dataclasses
from datetime import timedelta

import pytest

from algotrade.core.time.calendar import previous_session
from algotrade.services.preview.options.calls import (
    STRIKES_EACH,
    CallRow,
    CallsPreview,
    Dividend,
    preview_calls,
)
from algotrade.services.read.values import Unknown, UnknownCode
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import chain_rows, write_chains, write_curve, write_rows
from tests.unit.services.read.instruments.conftest import D1, context, store_with

AAA = "EQ:AAA"
R = 0.03
DAYS = (7, 14, 30, 45, 60)
EXPIRIES = {D1 + timedelta(days=d): 0.30 for d in DAYS}
STRIKES = tuple(float(k) for k in range(80, 125, 1))
EX_DATE = D1 + timedelta(days=20)
FORBIDDEN = {"bid", "ask", "last", "size", "bid_size", "ask_size", "volume"}


def chain(writer: StoreWriter) -> None:
    write_chains(writer, D1, chain_rows(AAA, D1, 100.0, EXPIRIES, R, strikes=STRIKES), {AAA: 100.0})
    write_curve(writer, D1, R)


def dividend(amount: float) -> object:
    def write(writer: StoreWriter) -> None:
        chain(writer)
        write_rows(
            writer, "rollups/instrument/dividend_schedule@v1", D1,
            [{"instrument_id": AAA, "dividend_status": "SCHEDULED", "next_ex_date": EX_DATE,
              "next_div_amount": amount, "days_to_ex_date": 20, "next_pay_date": None}],
        )  # fmt: skip

    return write


def calls(*writes: object, shares: int = 250, price: float = 98.0) -> CallsPreview | Unknown:
    reader = store_with(*writes)  # type: ignore[arg-type]
    return preview_calls(context(reader), AAA, shares, price)


def good(found: CallsPreview | Unknown) -> CallsPreview:
    assert isinstance(found, CallsPreview), found
    return found


def test_rows_are_the_bucket_expiries_with_strikes_around_the_price() -> None:
    p = good(calls(chain))
    assert sorted({r.days for r in p.rows}) == [14, 30, 45]
    for days in (14, 30, 45):
        strikes = [r.strike for r in p.rows if r.days == days]
        assert strikes == sorted(strikes) and len(strikes) == STRIKES_EACH
        assert all(0.95 * 98.0 <= k <= 110.0 for k in strikes)
    assert (p.contracts, p.shares, p.price) == (2, 250, 98.0)
    assert p.above_price == pytest.approx(100 / 98 - 1)


def test_the_figures_are_per_share_at_the_mid_over_the_traders_price() -> None:
    p = good(calls(chain))
    for row, total in zip(p.rows, p.premium_total, strict=True):
        assert row.premium_over_price == pytest.approx(row.premium / 98.0)
        assert row.if_called == pytest.approx((row.strike + row.premium - 98.0) / 98.0)
        assert row.below_price is (row.strike < 98.0)
        assert total == pytest.approx(row.premium * 100 * 2)
    assert any(r.below_price for r in p.rows)


def test_under_a_hundred_shares_is_no_contract() -> None:
    p = good(calls(chain, shares=60))
    assert p.contracts == 0 and all(t is None for t in p.premium_total)


def test_a_known_dividend_dates_the_ex_day_and_flags_early_exercise_in_the_money() -> None:
    p = good(calls(dividend(5.0)))
    assert p.dividend == Dividend(EX_DATE, 5.0, previous_session(EX_DATE))
    for r in p.rows:
        assert r.ex_div_before_expiry is (r.expiry >= EX_DATE)
        if not r.ex_div_before_expiry or r.strike >= 100.0:
            assert r.early_exercise_risk is False
    # a 5-dollar dividend is more than the time value left in an in-the-money call
    assert any(r.early_exercise_risk for r in p.rows if r.strike < 100.0 and r.days >= 30)
    small = good(calls(dividend(0.01)))
    assert not any(r.early_exercise_risk for r in small.rows)


def test_no_announced_dividend_is_unknown_never_false() -> None:
    p = good(calls(chain))
    assert isinstance(p.dividend, Unknown)
    assert all(r.ex_div_before_expiry is None and r.early_exercise_risk is None for r in p.rows)


def test_no_vendor_quote_is_on_any_type() -> None:
    for cls in (CallsPreview, CallRow, Dividend):
        assert not {f.name for f in dataclasses.fields(cls)} & FORBIDDEN


def test_a_name_with_no_chain_rows_is_unknown() -> None:
    def other(writer: StoreWriter) -> None:
        rows = chain_rows("EQ:BBB", D1, 100.0, EXPIRIES, R, strikes=STRIKES)
        write_chains(writer, D1, rows, {"EQ:BBB": 100.0})
        write_curve(writer, D1, R)

    found = calls(other)
    assert isinstance(found, Unknown) and found.code is UnknownCode.NO_ROW
