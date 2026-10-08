"""``SymbolResolver``: one place that turns tickers into ids (ADR 0018)."""

import pandas as pd

from algotrade.data.resolver import SymbolResolver


def test_active_listing_wins_a_reused_ticker() -> None:
    reference = pd.DataFrame(
        {
            "instrument_id": ["EQ:NEWCO", "EQ:OLDCO"],
            "symbol": ["ABC", "ABC"],
            "status": ["ACTIVE", "DELISTED"],
        }
    )
    resolver = SymbolResolver.from_reference(reference)
    assert resolver.id_for(" abc ") == "EQ:NEWCO"
    assert resolver.knows("abc") and not resolver.knows("XYZ")
    assert resolver.ids_for(["ABC", "XYZ"]) == {"ABC": "EQ:NEWCO", "XYZ": "EQ:XYZ"}
    assert resolver.symbol_for("EQ:OLDCO") == "ABC"
    assert resolver.symbol_for("EQ:NOPE") is None


def test_reference_without_status_and_empty_reference() -> None:
    plain = SymbolResolver.from_reference(
        pd.DataFrame({"instrument_id": ["EQ:BBG1"], "symbol": ["AAPL"]})
    )
    assert plain.id_for("AAPL") == "EQ:BBG1"
    empty = SymbolResolver.from_reference(pd.DataFrame(columns=["instrument_id", "symbol"]))
    assert empty.snapshot is None and empty.id_for("aapl") == "EQ:AAPL"


def test_resolve_replaces_existing_ids_and_counts_unknown() -> None:
    resolver = SymbolResolver.from_reference(
        pd.DataFrame({"instrument_id": ["EQ:BBG1"], "symbol": ["AAPL"]})
    )
    frame = pd.DataFrame({"instrument_id": ["EQ:AAPL", "x"], "symbol": ["AAPL", "Q"]})
    out, unknown = resolver.resolve(frame)
    assert list(out.columns) == ["instrument_id", "symbol"]
    assert list(out["instrument_id"]) == ["EQ:BBG1", "EQ:Q"] and unknown == 1
    empty, none = resolver.resolve(frame.iloc[:0])
    assert empty.empty and none == 0


def _listings() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "instrument_id": ["EQ:TIINGO:OLD1", "EQ:TIINGO:NEW2", None, "EQ:TIINGO:OPEN3"],
            "ticker": ["ABC", "ABC", "ZZZ", "OPEN"],
            "start_date": pd.to_datetime(["2005-01-03", "2014-06-02", "2010-01-04", "2001-01-02"]),
            "end_date": pd.to_datetime(["2013-12-31", "2020-03-02", "2012-01-03", None]),
        }
    )


def test_from_listings_resolves_a_recycled_ticker_by_the_session() -> None:
    from datetime import date  # noqa: PLC0415

    early = SymbolResolver.from_listings(_listings(), date(2010, 5, 3))
    late = SymbolResolver.from_listings(_listings(), date(2016, 5, 3))
    assert early.id_for("abc") == "EQ:TIINGO:OLD1"
    assert late.id_for("abc") == "EQ:TIINGO:NEW2"
    assert early.symbol_for("EQ:TIINGO:OLD1") == "ABC"
    assert late.knows("OPEN") and late.id_for("OPEN") == "EQ:TIINGO:OPEN3"


def test_from_listings_skips_rows_without_an_id_and_gaps() -> None:
    from datetime import date  # noqa: PLC0415

    gap = SymbolResolver.from_listings(_listings(), date(2014, 1, 6))  # between the two ABCs
    assert not gap.knows("ABC") and gap.id_for("ABC") == "EQ:ABC"
    assert not gap.knows("ZZZ")  # no id yet
    assert SymbolResolver.from_listings(None, date(2020, 1, 2)).ids == {}
