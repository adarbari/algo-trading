"""Buying power for a sold option on exactly the session's chain: cash-secured and the exchange
minimum (Reg-T, the mockup's figures), the premium's share of each, the size against the day's
volume and open interest, the put's stress over the worst stored episode (UNKNOWN when none),
derived figures only and the UNKNOWN cases."""

import dataclasses
from datetime import timedelta

import pytest

from algotrade.services.preview.options.margin import (
    REG_T,
    MarginPreview,
    Stress,
    preview_margin,
    reg_t_per_share,
)
from algotrade.services.preview.options.pool import Contract
from algotrade.services.read.values import Unknown, UnknownCode
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import chain_rows, write_chains, write_curve, write_rows
from tests.unit.services.read.instruments.conftest import D1, context, store_with

AAA = "EQ:AAA"
R = 0.03
EXPIRY = D1 + timedelta(days=14)
STRIKES = tuple(float(k) for k in range(80, 121, 5))
PUT = Contract("put", 95.0, EXPIRY)
FORBIDDEN = {"bid", "ask", "last", "size", "bid_size", "ask_size", "volume"}


def chain(writer: StoreWriter) -> None:
    rows = chain_rows(AAA, D1, 100.0, {EXPIRY: 0.3}, R, strikes=STRIKES, oi=800.0)
    write_chains(writer, D1, rows, {AAA: 100.0})
    write_curve(writer, D1, R)


def episodes(writer: StoreWriter) -> None:
    chain(writer)
    write_rows(
        writer, "rollups/instrument/episode_behaviour@v1", D1,
        [{"instrument_id": AAA, "dd_covid_2020": -0.34, "dd_hikes_2022": -0.21,
          "dd_tariffs_2025": None}],
    )  # fmt: skip


def margin(*writes: object, contract: Contract = PUT, n: int = 5) -> MarginPreview | Unknown:
    reader = store_with(*writes)  # type: ignore[arg-type]
    return preview_margin(context(reader), AAA, contract, n)


def good(found: MarginPreview | Unknown) -> MarginPreview:
    assert isinstance(found, MarginPreview), found
    return found


def test_reg_t_matches_the_published_rule() -> None:
    # The mockup: ORBT at 84.20, put 80.5, mid 0.59 -> 13.73 a share (the 20% leg).
    assert reg_t_per_share("put", 84.2, 80.5, 0.59) == pytest.approx(13.73)
    # Far out of the money the 10% floor takes over: 10% of the strike for a put ...
    assert reg_t_per_share("put", 100.0, 50.0, 0.10) == pytest.approx(5.10)
    # ... and of the underlying's price for a call.
    assert reg_t_per_share("call", 100.0, 150.0, 0.10) == pytest.approx(10.10)
    assert reg_t_per_share("call", 100.0, 105.0, 1.0) == pytest.approx(16.0)


def test_cash_secured_and_margin_held_for_five_puts() -> None:
    p = good(margin(chain))
    assert (p.rule, p.contracts, p.days, p.priced_at) == (REG_T, 5, 14, 100.0)
    assert p.cash_secured == pytest.approx(95.0 * 100 * 5)
    assert p.margin_held == pytest.approx(reg_t_per_share("put", 100.0, 95.0, p.premium) * 500)
    assert p.premium_total == pytest.approx(p.premium * 500)
    assert p.premium_over_cash == pytest.approx(p.premium_total / p.cash_secured)
    assert p.premium_over_margin == pytest.approx(p.premium_total / p.margin_held)
    assert p.margin_held < p.cash_secured


def test_a_calls_cash_is_the_shares_held_and_its_margin_the_naked_call_minimum() -> None:
    p = good(margin(episodes, contract=Contract("call", 105.0, EXPIRY)))
    assert p.cash_secured == pytest.approx(100.0 * 500) and p.stress is None
    naked = reg_t_per_share("call", 100.0, 105.0, p.premium) * 500
    assert p.margin_held == pytest.approx(naked)


def test_size_is_against_the_days_volume_and_open_interest() -> None:
    p = good(margin(chain))
    assert p.volume_share == pytest.approx(5 / 10.0)  # the helper quotes 10 a day
    assert p.open_interest_share == pytest.approx(5 / 800.0)


def test_the_stress_is_the_worst_stored_episode_and_unknown_without_one() -> None:
    p = good(margin(episodes))
    assert isinstance(p.stress, Stress) and p.stress.episode == "covid_2020"
    assert p.stress.drop == pytest.approx(-0.34)
    assert p.stress.in_the_money == pytest.approx((95.0 - 66.0) * 500, rel=1e-5)
    none = good(margin(chain))
    assert isinstance(none.stress, Unknown)


def test_no_vendor_quote_is_on_any_type() -> None:
    for cls in (MarginPreview, Stress, Contract):
        assert not {f.name for f in dataclasses.fields(cls)} & FORBIDDEN


def test_a_contract_not_listed_or_expired_is_not_applicable() -> None:
    for contract in (Contract("put", 96.0, EXPIRY), Contract("put", 95.0, D1)):
        found = margin(chain, contract=contract)
        assert isinstance(found, Unknown) and found.code is UnknownCode.NOT_APPLICABLE
