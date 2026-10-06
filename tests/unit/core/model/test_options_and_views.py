from datetime import date

import pytest

from algotrade.core.model.instruments import (
    AssetClass,
    equity_id,
    instrument_id,
    is_figi_id,
    key_of,
)
from algotrade.core.model.options import (
    OptionRight,
    is_standard_root,
    parse_osi,
    standard_monthly_expiries,
    third_friday,
)
from algotrade.core.views.feature_view import FeatureView


def test_parse_osi() -> None:
    osi = parse_osi("SPY261231C00586000")
    assert osi is not None
    assert (osi.root, osi.expiry, osi.right, osi.strike) == (
        "SPY",
        date(2026, 12, 31),
        OptionRight.CALL,
        586.0,
    )
    assert parse_osi("BRK.B261120P00450500").strike == 450.5  # type: ignore[union-attr]
    assert parse_osi("not-an-option") is None


def test_standard_root() -> None:
    assert is_standard_root("BRKB", "BRK.B")
    assert not is_standard_root("AAPL1", "AAPL")


def test_third_friday() -> None:
    assert third_friday(2026, 10) == date(2026, 10, 16)
    assert third_friday(2026, 5) == date(2026, 5, 15)


def test_monthly_falls_back_to_thursday_on_holiday() -> None:
    # 2026-06-19 (third Friday) is Juneteenth: the monthly moves to Thursday 06-18.
    listed = [date(2026, 6, 12), date(2026, 6, 18), date(2026, 6, 26), date(2026, 7, 17)]
    assert standard_monthly_expiries(listed) == {date(2026, 6, 18), date(2026, 7, 17)}
    assert standard_monthly_expiries([date(2026, 6, 12)]) == set()


def test_instrument_ids() -> None:
    assert instrument_id(AssetClass.EQUITY, " spy ") == "EQ:SPY"
    assert key_of("OPT:SPY261231C00586000") == "SPY261231C00586000"
    with pytest.raises(ValueError, match="empty"):
        instrument_id(AssetClass.EQUITY, " ")
    with pytest.raises(ValueError, match="not an instrument"):
        key_of("SPY")


def test_equity_ids_prefer_the_figi() -> None:
    assert equity_id("aapl", "BBG000B9XRY4") == "EQ:BBG000B9XRY4"
    assert equity_id("aapl") == "EQ:AAPL"
    assert equity_id("AAPL", " ") == "EQ:AAPL"
    assert is_figi_id("EQ:BBG000B9XRY4", "BBG000B9XRY4")
    assert not is_figi_id("EQ:AAPL", "BBG000B9XRY4")
    assert not is_figi_id("EQ:AAPL", None)


def test_feature_view_is_read_only_and_sorted() -> None:
    view = FeatureView(date(2026, 10, 2), {"EQ:B": {"x": 1}, "EQ:A": {"x": 2}})
    assert view.instruments == ("EQ:A", "EQ:B")
    assert list(view) == ["EQ:A", "EQ:B"]
    assert "EQ:A" in view
    assert view.get("EQ:A", "x") == 2
    assert view.get("EQ:Z", "x") is None
    assert view.as_of == date(2026, 10, 2)
    with pytest.raises(TypeError):
        view.row("EQ:A")["x"] = 3  # type: ignore[index]


def test_index_and_macro_ids_are_minted_from_their_keys() -> None:
    from algotrade.core.model.instruments import index_id, macro_id  # noqa: PLC0415

    assert (index_id("spx"), macro_id("T10Y3M")) == ("IDX:SPX", "MACRO:T10Y3M")
    assert key_of(macro_id("UNRATE")) == "UNRATE"
    with pytest.raises(ValueError, match="empty"):
        index_id(" ")
