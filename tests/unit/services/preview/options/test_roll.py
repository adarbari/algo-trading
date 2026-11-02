"""Rolling a sold option on exactly the session's chain: the buy-back at the mid, rolls to later
expiries at the sold strike or further out of the money, credits only unless debits are asked
for, the same-delta pick, the breakeven only with the price sold at, derived figures only (no
vendor quote on any type) and every UNKNOWN case."""

import dataclasses
from datetime import date, timedelta

import pytest

from algotrade.services.preview.options.roll import (
    MAX_EXPIRIES,
    Contract,
    Roll,
    RollPreview,
    preview_roll,
)
from algotrade.services.read.values import Unknown, UnknownCode
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import chain_rows, quote_row, write_chains, write_curve, write_rows
from tests.unit.services.read.instruments.conftest import D0, D1, context, store_with

AAA = "EQ:AAA"
R = 0.03
DAYS = (7, 14, 21, 28, 35, 49, 63, 91, 150)
EXPIRIES = {D1 + timedelta(days=d): 0.30 for d in DAYS}
STRIKES = (*(float(k) for k in range(70, 131, 5)), 97.5, 92.5)
SOLD = Contract("put", 95.0, D1 + timedelta(days=7))
FORBIDDEN = {"bid", "ask", "last", "size", "bid_size", "ask_size", "volume"}


def chain(writer: StoreWriter) -> None:
    write_chains(writer, D1, chain_rows(AAA, D1, 100.0, EXPIRIES, R, strikes=STRIKES), {AAA: 100.0})
    write_curve(writer, D1, R)


def roll(*writes: object, contract: Contract = SOLD, **kw: object) -> RollPreview | Unknown:
    reader = store_with(*writes)  # type: ignore[arg-type]
    return preview_roll(context(reader), AAA, contract, **kw)  # type: ignore[arg-type]


def good(found: RollPreview | Unknown) -> RollPreview:
    assert isinstance(found, RollPreview), found
    return found


def test_the_buy_back_is_the_mid_and_the_rolls_go_to_later_expiries_further_out() -> None:
    p = good(roll(chain, sold_at=1.0))
    assert (p.priced_at, p.days_left, p.session) == (100.0, 7, D1)
    assert p.above_strike == pytest.approx(100 / 95 - 1)
    assert p.over_collected == pytest.approx(p.buy_back - 1.0)
    assert p.delta < 0  # a put's delta, ours
    expiries = sorted({r.expiry for r in p.rolls})
    assert all(e > SOLD.expiry for e in expiries) and len(expiries) <= MAX_EXPIRIES
    assert all((e - D1).days <= 120 for e in expiries)  # 150 days is past the window
    for e in expiries:
        strikes = [r.strike for r in p.rolls if r.expiry == e]
        assert all(85.5 <= k <= 95.0 for k in strikes) and len(strikes) <= 3
        assert strikes == sorted(strikes, reverse=True)  # the sold strike first
    assert all(r.extra_credit > 0 for r in p.rolls)


def test_the_new_breakeven_is_every_credit_off_the_strike_and_none_without_the_price_sold() -> None:
    p = good(roll(chain, sold_at=1.0))
    for r in p.rolls:
        assert r.new_breakeven == pytest.approx(r.strike - (1.0 + r.extra_credit))
        days = (r.expiry - SOLD.expiry).days
        assert r.credit_per_extra_day == pytest.approx(r.extra_credit / days)
    assert all(r.new_breakeven is None for r in good(roll(chain)).rolls)
    assert good(roll(chain)).over_collected is None


def test_rolls_that_cost_money_show_only_when_asked() -> None:
    expensive = Contract("put", 130.0, D1 + timedelta(days=7))  # deep in the money: a far
    # lower strike costs less than buying it back
    credits = good(roll(chain, contract=expensive))
    every = good(roll(chain, contract=expensive, include_debits=True))
    assert len(every.rolls) > len(credits.rolls)
    assert any(r.extra_credit <= 0 for r in every.rolls)


def test_same_delta_keeps_one_strike_per_expiry_nearest_the_sold_delta() -> None:
    p = good(roll(chain, same_delta=True))
    expiries = [r.expiry for r in p.rolls]
    assert len(expiries) == len(set(expiries))
    every = good(roll(chain, include_debits=True))
    for r in p.rolls:
        assert all(abs(abs(r.delta) - abs(p.delta)) <= abs(abs(o.delta) - abs(p.delta)) + 1e-9
                   for o in every.rolls if o.expiry == r.expiry)  # fmt: skip


def test_a_call_rolls_up_and_out() -> None:
    call = Contract("call", 105.0, D1 + timedelta(days=7))
    p = good(roll(chain, contract=call, sold_at=1.0, include_debits=True))
    assert p.delta > 0 and all(105.0 <= r.strike <= 115.5 for r in p.rolls)
    assert all(r.new_breakeven == pytest.approx(r.strike + 1.0 + r.extra_credit) for r in p.rolls)


def test_a_report_inside_the_new_expiry_is_flagged_and_unknown_is_never_false() -> None:
    def earnings(writer: StoreWriter) -> None:
        chain(writer)
        write_rows(
            writer, "rollups/instrument/earnings@v1", D1,
            [{"instrument_id": AAA, "next_earnings_date": D1 + timedelta(days=30),
              "days_to_earnings": 20}],
        )  # fmt: skip

    p = good(roll(earnings))
    assert {r.expiry: r.report_inside for r in p.rolls} == {
        r.expiry: (r.expiry - D1).days >= 30 for r in p.rolls
    }
    unknown = good(roll(chain))
    assert all(r.report_inside is None and r.report_inside_unknown for r in unknown.rolls)


def test_no_vendor_quote_is_on_any_type() -> None:
    for cls in (RollPreview, Roll, Contract):
        assert not {f.name for f in dataclasses.fields(cls)} & FORBIDDEN


def test_a_contract_not_listed_tonight_is_not_applicable() -> None:
    missing = roll(chain, contract=Contract("put", 96.0, SOLD.expiry))
    assert isinstance(missing, Unknown) and missing.code is UnknownCode.NOT_APPLICABLE
    expired = roll(chain, contract=Contract("put", 95.0, D1))
    assert isinstance(expired, Unknown) and expired.code is UnknownCode.NOT_APPLICABLE


def test_a_one_sided_sold_contract_is_illiquid() -> None:
    def one_sided(writer: StoreWriter) -> None:
        rows = [r for r in chain_rows(AAA, D1, 100.0, EXPIRIES, R, strikes=STRIKES)
                if not (r["expiry"] == SOLD.expiry and r["strike"] == 95.0)]  # fmt: skip
        rows.append(quote_row(AAA, D1, SOLD.expiry, "P", 95.0, 0.0, 1.0))
        write_chains(writer, D1, rows, {AAA: 100.0})
        write_curve(writer, D1, R)

    found = roll(one_sided)
    assert isinstance(found, Unknown) and found.code is UnknownCode.ILLIQUID


def test_only_the_sessions_chain_is_read_never_an_older_one() -> None:
    def older(writer: StoreWriter) -> None:
        rows = chain_rows(AAA, D0, 100.0, {SOLD.expiry: 0.3}, R, strikes=STRIKES)
        write_chains(writer, D0, rows, {AAA: 100.0})
        write_curve(writer, D1, R)

    found = roll(older)
    assert isinstance(found, Unknown) and found.code is UnknownCode.NO_PARTITION


def test_session_is_the_contexts() -> None:
    assert good(roll(chain)).session == date(2026, 10, 1) == D1
