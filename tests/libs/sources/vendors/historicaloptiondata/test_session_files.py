"""HistoricalOptionData session files parse (ADR 0086): both file variants (a daily zip's
``MM/DD/YYYY 16:00`` stamps and a monthly zip's date-only ones), the 16:00 New York instant, the
OSI cross-check, nothing filtered, and the stock history files."""

import io
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from algotrade_sources.vendors.historicaloptiondata.session_files import (
    parse_option_stats,
    parse_options,
    parse_stock_quotes,
)
from algotrade_sources.vendors.historicaloptiondata.stock_history import (
    parse_dividends,
    parse_splits,
)

FIXTURES = Path(__file__).parents[4] / "fixtures" / "sources" / "historicaloptiondata"


def stream(name: str) -> io.BytesIO:
    return io.BytesIO((FIXTURES / name).read_bytes())


def test_a_daily_file_has_a_sixteen_hundred_stamp_in_new_york_time() -> None:
    parsed = parse_options(stream("options_20190815.csv"))
    assert parsed is not None
    assert parsed.session == date(2019, 8, 15)
    assert set(parsed.options["ts"]) == {datetime(2019, 8, 15, 20, 0, tzinfo=UTC)}  # EDT
    assert parsed.notes["off_hours"] == 0
    assert parsed.notes["file_rows"] == 41
    assert parsed.notes["rows"] == len(parsed.options) == 37  # four adjusted-series rows out


def test_a_monthly_file_without_a_time_is_the_same_snapshot() -> None:
    parsed = parse_options(stream("options_20190816.csv"))
    assert parsed is not None
    assert parsed.session == date(2019, 8, 16)
    assert set(parsed.options["ts"]) == {datetime(2019, 8, 16, 20, 0, tzinfo=UTC)}
    assert parsed.notes["assumed_time"] == 41


def test_contract_ids_are_the_osi_ids_the_cboe_pull_uses() -> None:
    parsed = parse_options(stream("options_20190815.csv"))
    assert parsed is not None
    row = parsed.options[parsed.options["instrument_id"] == "OPT:SPY190920P00284000"].iloc[0]
    assert (row["symbol"], row["root"], row["right"], row["strike"]) == ("SPY", "SPY", "P", 284.0)
    assert row["expiry"] == date(2019, 9, 20)
    assert {"SPXW"} == set(parsed.options.loc[parsed.options["root"] == "SPXW", "root"])
    assert parsed.notes["unknown_right"] == 0


def test_a_symbol_that_disagrees_with_its_columns_is_counted_and_its_id_is_built_from_them() -> (
    None
):
    parsed = parse_options(stream("options_20190815.csv"))
    assert parsed is not None
    assert parsed.notes["osi_mismatch"] == 1
    assert "OPT:AAPL190816C00210000" in set(parsed.options["instrument_id"])  # the columns win


def test_an_adjusted_series_is_excluded_and_counted() -> None:
    parsed = parse_options(stream("options_20190815.csv"))
    assert parsed is not None
    assert parsed.notes["nonstandard_series"] == 4
    assert not parsed.options["root"].eq("AAPL1").any()


def test_nothing_is_filtered_and_the_quality_counts_are_reported() -> None:
    parsed = parse_options(stream("options_20190815.csv"))
    assert parsed is not None
    zero_bids = int((parsed.options["bid"] == 0).sum())
    assert parsed.notes["zero_bid"] == zero_bids
    assert parsed.notes["crossed"] == 0
    assert parsed.notes["duplicate_contracts"] == 0
    assert parsed.notes["underlyings"] == 4


def test_a_file_spanning_two_days_is_refused() -> None:
    first = (FIXTURES / "options_20190815.csv").read_text().splitlines()
    second = (FIXTURES / "options_20190816.csv").read_text().splitlines()
    mixed = "\n".join([*first, *second[1:3]])
    with pytest.raises(ValueError, match="spans 2 days"):
        parse_options(io.BytesIO(mixed.encode()))


def test_an_osi_suffix_that_disagrees_with_the_columns_is_counted() -> None:
    lines = (FIXTURES / "options_20190815.csv").read_text().splitlines()
    lines[1] = lines[1].replace("SPX190920C02840000", "SPX190920C02841000", 1)
    parsed = parse_options(io.BytesIO("\n".join(lines).encode()))
    assert parsed is not None and parsed.notes["osi_mismatch"] == 2


def test_an_empty_file_is_none() -> None:
    header = (FIXTURES / "options_20190815.csv").read_text().splitlines()[0]
    assert parse_options(io.BytesIO(header.encode())) is None


def test_stock_quotes_and_option_stats() -> None:
    quotes = parse_stock_quotes(stream("stockquotes_20190815.csv"))
    assert list(quotes.columns) == ["symbol", "open", "high", "low", "close", "volume"]
    assert quotes.set_index("symbol").loc["A", "close"] == 69.59
    assert "adjustedclose" not in parse_stock_quotes(stream("stockquotes_20190816.csv")).columns
    stats = parse_option_stats(stream("optionstats_20190816.csv"))
    assert {"iv30call", "iv30put", "iv30mean", "callvol", "putvol", "calloi", "putoi"} <= set(
        stats.columns
    )
    assert stats["symbol"].is_unique


def test_dividends_and_splits_are_headerless_with_new_per_old_ratios() -> None:
    dividends = parse_dividends(stream("dividends.csv"))
    assert dividends.loc[dividends["symbol"] == "AAPL", "amount"].iloc[0] == 0.5
    assert dividends["ex_date"].iloc[0] == date(2019, 12, 30)
    splits = parse_splits(stream("stocksplits.csv")).set_index("symbol")
    assert splits.loc["QQA", "ratio"] == 1.5 and splits.loc["QQA", "text"] == "3 for 2"
    assert splits.loc["QQB", "ratio"] == pytest.approx(1 / 3, abs=1e-3)
    assert splits.loc["QQC", "ex_date"] == date(2017, 11, 4)
