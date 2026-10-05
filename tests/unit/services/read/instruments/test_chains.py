"""An underlying's option chain for exactly the session (session grain): expiries with their
days, strikes, the run's status and one expiry's quotes; none for the session is no chain,
never an older one; the chain's rows are read once per publish for chain and quotes."""

from datetime import date, timedelta

from algotrade.services.read.instruments.chains import OptionExpiry, load_chains, load_quotes
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import chain_rows, write_chains, write_rows
from tests.unit.services.read.instruments.conftest import D0, D1, context, store_with

NEAR, FAR = D1 + timedelta(days=30), D1 + timedelta(days=58)


def _chains(writer: StoreWriter) -> None:
    write_chains(writer, D0, chain_rows("EQ:ETFX", D0, 50.0, {NEAR: 0.2}, 0.03), {"EQ:ETFX": 50.0})
    rows = chain_rows("EQ:AAA", D1, 100.0, {NEAR: 0.25, FAR: 0.27}, 0.03, strikes=(95, 100, 105))
    write_chains(writer, D1, rows, {"EQ:AAA": 100.0})
    write_rows(writer, "chains/status", D1, [{"instrument_id": "EQ:AAA", "status": "OK"}])


def test_the_chain_of_the_session() -> None:
    ctx = context(store_with(_chains))
    chain = load_chains(ctx, ["EQ:AAA"])["EQ:AAA"]
    assert chain is not None
    assert (chain.underlying_id, chain.session, chain.status) == ("EQ:AAA", D1, "OK")
    assert chain.expiries == (OptionExpiry(NEAR, 30), OptionExpiry(FAR, 58))
    assert chain.strikes == (95.0, 100.0, 105.0)


def test_one_expiry_of_quotes_by_strike_then_right() -> None:
    ctx = context(store_with(_chains))
    quotes = load_quotes(ctx, ["EQ:AAA", "EQ:ETFX"], NEAR)
    aaa = quotes["EQ:AAA"]
    assert [(q.strike, q.right) for q in aaa] == [
        (95.0, "C"), (95.0, "P"), (100.0, "C"), (100.0, "P"), (105.0, "C"), (105.0, "P"),
    ]  # fmt: skip
    assert {q.expiry for q in aaa} == {NEAR}
    assert aaa[0].bid is not None and aaa[0].bid < aaa[0].ask  # type: ignore[operator]
    assert aaa[0].last is None  # not stored: None, not NaN
    assert quotes["EQ:ETFX"] == ()  # its only chain is D0's
    assert load_quotes(ctx, ["EQ:AAA"], date(2027, 1, 1)) == {"EQ:AAA": ()}


def test_an_older_chain_is_never_shown_for_the_session() -> None:
    reader = store_with(_chains)
    assert load_chains(context(reader), ["EQ:ETFX"]) == {"EQ:ETFX": None}  # D0's only
    on_d0 = load_chains(context(reader, D0), ["EQ:ETFX", "EQ:AAA"])
    assert on_d0["EQ:ETFX"] is not None and on_d0["EQ:ETFX"].status is None  # no status row
    assert on_d0["EQ:AAA"] is None  # D1's chain is later than D0


def test_no_chain_partition_for_the_session_is_no_chain() -> None:
    ctx = context(store_with(), date(2026, 10, 2))
    assert load_chains(ctx, ["EQ:AAA"]) == {"EQ:AAA": None}
    assert load_quotes(ctx, ["EQ:AAA"], NEAR) == {"EQ:AAA": ()}


def test_the_rows_are_read_once_per_publish() -> None:
    reader = store_with(_chains)
    ctx = context(reader)
    load_chains(ctx, ["EQ:AAA"])
    key = ("chain-rows", D1, ("EQ:AAA",), reader.visible_seq())
    assert ctx.cache.get(key) is not None
