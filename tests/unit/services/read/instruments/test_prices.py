"""Daily bars over an explicit window (range grain): ``end`` the session's date unless named,
adjusted for the splits in the window unless asked not to, empty outside the stored range."""

from datetime import date

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.read.instruments.prices import Adjustment, PriceBar, load_prices
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import write_split
from tests.unit.services.read.instruments.conftest import D0, D1, context, store_with


def _split(writer: StoreWriter) -> None:
    write_split(writer, "EQ:AAA", D1, 2.0, D1)


def test_bars_up_to_the_session_by_default() -> None:
    ctx = context(store_with())
    found = load_prices(ctx, ["EQ:AAA", "EQ:ETFX"], date(2026, 9, 1))
    aaa = found["EQ:AAA"]
    assert (aaa.instrument_id, aaa.adjustment, aaa.start, aaa.end) == (
        "EQ:AAA",
        Adjustment.SPLITS,
        date(2026, 9, 1),
        D1,
    )
    assert aaa.bars == (
        PriceBar(D0, 1.0, 1.0, 1.0, 1.0, 1.0, None),
        PriceBar(D1, 1.0, 1.0, 1.0, 1.0, 1.0, None),
    )
    assert found["EQ:ETFX"].bars == ()  # no bars stored for it


def test_an_explicit_end_and_an_empty_window() -> None:
    ctx = context(store_with())
    assert [b.session for b in load_prices(ctx, ["EQ:AAA"], D0, D0)["EQ:AAA"].bars] == [D0]
    assert load_prices(ctx, ["EQ:AAA"], date(2010, 1, 1), date(2010, 2, 1))["EQ:AAA"].bars == ()


def test_split_adjusted_unless_asked() -> None:
    ctx = context(store_with(_split))
    adjusted = load_prices(ctx, ["EQ:AAA"], D0)["EQ:AAA"].bars
    raw = load_prices(ctx, ["EQ:AAA"], D0, adjustment=Adjustment.NONE)["EQ:AAA"].bars
    assert (adjusted[0].close, raw[0].close) == (0.5, 1.0)  # before the split: halved
    assert adjusted[1].close == raw[1].close == 1.0


def test_an_end_after_the_session_is_refused() -> None:
    ctx = context(store_with(), D0)
    with pytest.raises(ConfigurationError, match="after the session"):
        load_prices(ctx, ["EQ:AAA"], D0, D1)
