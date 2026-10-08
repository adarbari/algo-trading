"""``equity_id`` is the one ``EQ:`` constructor: FIGI, then permaTicker, then symbol (ADR 0018)."""

import pytest

from algotrade.core.model.instruments import equity_id, key_of


def test_figi_beats_perma_ticker_beats_symbol() -> None:
    assert equity_id("AAPL", "BBG000B9XRY4", "000000001") == "EQ:BBG000B9XRY4"
    assert equity_id("AAPL", None, "000000001") == "EQ:TIINGO:000000001"
    assert equity_id("AAPL", " ", "") == "EQ:AAPL"
    assert equity_id("aapl") == "EQ:AAPL"


def test_a_symbol_never_contains_a_colon() -> None:
    # Fitness test: ``EQ:TIINGO:<perma>`` is a namespaced key, so a symbol that carried a
    # ':' could forge one ("TIINGO:X" -> EQ:TIINGO:X) and merge two securities.
    with pytest.raises(ValueError, match="never contains"):
        equity_id("TIINGO:000000001")


def test_a_namespaced_id_keeps_its_key() -> None:
    assert key_of(equity_id("OLD", None, "000000042")) == "TIINGO:000000042"
