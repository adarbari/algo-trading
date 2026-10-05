"""An ETF's holdings as of the issuer's date the session sees (issuer-dated grain): the latest
``as_of`` on or before the session, a later ``filed`` date invisible, ``as_of`` disclosed;
links to the universe; none for a stock."""

from datetime import date

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.read.instruments.holdings import load_holdings
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import write_rows
from tests.helpers.stored_frames import holdings_rows
from tests.unit.services.read.instruments.conftest import D0, D1, context, store_with

LATEST = date(2026, 9, 29)
LINES: list[tuple[str | None, str, float]] = [
    ("AAA", "AAA Holdings", 0.4),
    ("CAT", "Caterpillar", 0.3),
    (None, "US Dollar", 0.2),
    ("ZZZ", "Zeta", 0.1),
]


def _holdings(writer: StoreWriter) -> None:
    first = holdings_rows("EQ:ETFX", date(2026, 9, 28), LINES[:2])
    write_rows(writer, "holdings/etf", D0, first)
    latest = holdings_rows("EQ:ETFX", LATEST, LINES, total=500, linked={"AAA": "EQ:AAA"})
    # An N-PORT report for a later period, filed after the session: not known on D1.
    filed = holdings_rows("EQ:ETFX", D1, LINES[:1], filed=date(2026, 11, 30))
    write_rows(writer, "holdings/etf", D1, [*latest, *filed])


def test_the_top_holdings_with_links_total_date_and_source() -> None:
    found = load_holdings(context(store_with(_holdings)), ["EQ:ETFX"], 3)["EQ:ETFX"]
    assert found is not None
    assert (found.fund_id, found.as_of, found.total) == ("EQ:ETFX", LATEST, 500)
    assert [(h.rank, h.symbol, h.instrument_id, h.weight) for h in found.items] == [
        (1, "AAA", "EQ:AAA", 0.4),
        (2, "CAT", None, 0.3),  # printed with a ticker the universe does not have
        (3, None, None, 0.2),  # cash: name only
    ]
    assert found.items[0].asset_class == "Equity"


def test_the_session_sees_the_issuer_date_on_or_before_it() -> None:
    found = load_holdings(context(store_with(_holdings), D0), ["EQ:ETFX"], 10)["EQ:ETFX"]
    assert found is not None
    assert (found.as_of, found.total, len(found.items)) == (date(2026, 9, 28), 2, 2)


def test_an_etf_without_holdings_is_empty_and_a_stock_has_none() -> None:
    ctx = context(store_with())
    found = load_holdings(ctx, ["EQ:ETFX", "EQ:AAA", "EQ:ZZZ"], 10)
    assert found["EQ:ETFX"] is not None
    assert (found["EQ:ETFX"].as_of, found["EQ:ETFX"].items, found["EQ:ETFX"].total) == (
        None,
        (),
        0,
    )
    assert (found["EQ:AAA"], found["EQ:ZZZ"]) == (None, None)


def test_top_is_at_least_one() -> None:
    with pytest.raises(ConfigurationError, match="top"):
        load_holdings(context(store_with()), ["EQ:ETFX"], 0)
