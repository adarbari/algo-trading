"""The history's quotes as a Cboe chain (ADR 0084, F7): the declared columns of the chain tables,
the vendor's IV and delta never carried over, the spot of an index (no stock quote) from its option
rows, every row stamped with its partition's session and write instant, a name with no id left out,
one ``OK`` status row per underlying."""

from datetime import date

import pandas as pd

from algotrade.data.option_history.chain_frames import (
    OPTION_COLUMNS,
    UNDERLYING_COLUMNS,
    chain_option_quotes,
    chain_status,
    chain_underlying_quotes,
)

DAY = date(2019, 8, 16)
STAMP = pd.Timestamp("2026-11-04", tz="UTC")


def _quotes() -> pd.DataFrame:
    rows = []
    for symbol, uid, spot in (
        ("SPY", "EQ:SPY", 290.0),
        ("SPXW", "IDX:SPX", 2900.0),
        ("ZZZ", None, 5.0),
    ):
        for strike in (1.0, 2.0):
            rows.append({
                "instrument_id": f"OPT:{symbol}{strike}", "symbol": symbol, "underlying_id": uid,
                "ts": STAMP, "expiry": DAY, "right": "P", "strike": strike, "bid": 1.0, "ask": 1.2,
                "underlying_price": spot, "iv": 0.3, "delta": -0.2, "session_date": DAY,
                "knowledge_ts": STAMP, "source": "hod", "run_id": "r",
            })  # fmt: skip
    return pd.DataFrame(rows)


def test_option_rows_are_the_chain_columns_without_the_vendors_iv_and_delta() -> None:
    out = chain_option_quotes(_quotes())
    assert set(OPTION_COLUMNS) <= set(out.columns) and len(out) == 4  # ZZZ has no id
    assert out["iv"].isna().all() and out["delta"].isna().all()
    assert (out["session_date"] == DAY).all() and out["knowledge_ts"].notna().all()


def test_an_index_has_a_spot_from_its_option_rows_and_every_row_is_stamped() -> None:
    quotes = _quotes()
    under = pd.DataFrame([{
        "symbol": "SPY", "underlying_id": "EQ:SPY", "close": 291.0, "open": 1.0, "high": 1.0,
        "low": 1.0, "volume": 1.0, "session_date": DAY, "knowledge_ts": STAMP,
    }])  # fmt: skip
    out = chain_underlying_quotes(under, quotes).set_index("instrument_id")
    assert out.loc["EQ:SPY", "price"] == 291.0  # the vendor's close wins
    assert out.loc["IDX:SPX", "price"] == 2900.0  # no stock quote: the option rows' spot
    assert set(UNDERLYING_COLUMNS) <= set(out.reset_index().columns)
    assert out["session_date"].notna().all() and out["knowledge_ts"].notna().all()
    assert out["ts"].notna().all()


def test_the_status_is_ok_for_every_underlying_with_an_id() -> None:
    out = chain_status(_quotes())
    assert sorted(out["instrument_id"]) == ["EQ:SPY", "IDX:SPX"]
    assert set(out["status"]) == {"OK"}
