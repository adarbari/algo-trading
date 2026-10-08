"""``TiingoSupportedTickers`` on the SYNTHETIC supported-tickers file."""

from datetime import date

import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.vendors.tiingo.listings import (
    COLUMNS,
    TABLE,
    URL,
    TiingoSupportedTickers,
    parse_listings,
)
from tests.helpers.ingest_fakes import http_for
from tests.helpers.payloads import tiingo as payloads


def test_the_one_file_is_fetched_as_received() -> None:
    urls: list[str] = []
    zipped = payloads.supported_tickers_zip()
    source = TiingoSupportedTickers(http_for(lambda url: urls.append(url) or zipped))
    assert source.fetch(FetchRequest("supported_tickers")) == zipped
    assert urls == [URL]


def test_rows_are_filtered_mapped_and_the_recycled_ticker_keeps_both_listings() -> None:
    listings, dropped = parse_listings(payloads.supported_tickers_zip())
    assert list(listings.columns) == COLUMNS
    assert list(zip(listings["ticker"], listings["start_date"], strict=True)) == [
        ("AAA", date(2000, 1, 3)),
        ("BBB", date(2005, 3, 1)),
        ("ETFX", date(2008, 1, 2)),
        ("OLDM", date(2001, 5, 1)),
        ("RCY", date(2005, 1, 3)),
        ("RCY", date(2011, 3, 1)),
    ]
    rcy = listings[listings["ticker"] == "RCY"]
    assert rcy["end_date"].iloc[0] == date(2010, 12, 31) and rcy["end_date"].iloc[1] is None
    by = listings.set_index("ticker")
    assert by.loc["ETFX", "exchange"] == "ARCA" and by.loc["ETFX", "asset_type"] == "ETF"
    assert by.loc["OLDM", "exchange"] == "AMEX"  # NYSE MKT
    assert set(listings["perma_ticker"]) == {""}
    assert dropped == {
        "not_usd": 1, "other_exchange": 1, "other_asset_type": 1, "no_start_date": 1,
        "no_ticker": 0,
    }  # fmt: skip


def test_a_bare_csv_parses_too_and_normalize_exposes_the_frame_as_parsed() -> None:
    source = TiingoSupportedTickers(http_for(lambda url: b""))
    raw = payloads.SUPPORTED_TICKERS_SYNTHETIC.encode()
    normalized = source.normalize(FetchRequest("x", session_date=date(2026, 10, 5)), raw)
    assert normalized is not None and normalized.tables == {}
    assert len(normalized.parsed[TABLE]) == 6 and normalized.notes["dropped_not_usd"] == 1


def test_a_file_without_the_documented_header_is_an_error() -> None:
    with pytest.raises(ValueError, match="lacks columns"):
        parse_listings(b"symbol,name\nAAA,Triple A\n")


def test_a_live_name_stays_in_the_universe_after_the_pull_s_last_price_day() -> None:
    from algotrade.data.listings.universe import listed_asof  # noqa: PLC0415

    listings, _ = parse_listings(payloads.supported_tickers_zip())
    live = listings[listings["ticker"] == "AAA"]
    assert live["end_date"].isna().all()  # the file's latest endDate is stored open
    ids = live.assign(instrument_id="EQ:TIINGO:A")
    after = listed_asof(ids, date(2026, 12, 1), {"EQ:TIINGO:A"})
    assert list(after.instruments["ticker"]) == ["AAA"]
    gone = listings[listings["ticker"] == "OLDM"].assign(instrument_id="EQ:TIINGO:O")
    assert listed_asof(gone, date(2026, 12, 1), set()).instruments.empty  # delisted 2009: out
