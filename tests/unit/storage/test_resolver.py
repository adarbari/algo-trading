"""``SymbolResolver``: one place that turns tickers into ids (ADR 0018)."""

import pandas as pd

from algotrade.storage.resolver import SymbolResolver


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
