"""``fund_names``: the ticker and the kind a leveraged fund's name states."""

import pytest

from algotrade.features.rollups.reference.fund_names import name_kind, name_ticker


@pytest.mark.parametrize(
    ("name", "ticker"),
    [
        ("Direxion Daily TSLA Bull 2X Shares", "TSLA"),
        ("Direxion Daily AAPL Bear 1X Shares", "AAPL"),
        ("GraniteShares 2x Long NVDA Daily ETF", "NVDA"),
        ("Leverage Shares 2X Long AAPL Daily ETF", "AAPL"),
        ("Tradr 2X Short TSLA Daily ETF", "TSLA"),
        ("Direxion Daily BRK.B Bull 2X", "BRK.B"),
        ("MSFT 2X Bull ETF", "MSFT"),
        ("AXS TSLA Bear Daily ETF", "TSLA"),
        ("AXS Short Nvidia Daily ETF", None),
        ("GraniteShares 2X Long TSLA vs NVDA Daily ETF", None),  # a pair: no single reference
        ("Tradr 2X Long TSLA/NVDA Daily ETF", None),
        ("Direxion Daily AAPL & MSFT Bull 2X", None),
        ("Direxion Daily S&P 500 Bull 3X", None),  # S&P is not a pair of tickers
        ("T-Rex 2X Long Tesla Daily Target ETF", None),  # a company name is not read
        ("Direxion Daily S&P 500 Bull 3X Shares", None),
        ("ProShares UltraPro QQQ", None),
        ("DIREXION DAILY GOLD BULL 2X", None),  # all capitals: a word is not told from a ticker
        ("", None),
    ],
)
def test_ticker_in_the_spellings_fund_names_use(name: str, ticker: str | None) -> None:
    assert name_ticker(name) == ticker


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("ProShares UltraPro QQQ", "index"),
        ("Direxion Daily S&P 500 Bull 3X Shares", "index"),
        ("ProShares Ultra Russell2000", "index"),
        ("ProShares UltraPro Dow30", "index"),
        ("ProShares UltraShort 20+ Year Treasury", None),  # no keyword: says nothing
        ("Direxion Daily Semiconductor Bull 3X Shares", "sector"),
        ("Direxion Daily Gold Miners Index Bull 2X Shares", "sector"),  # sector before index
        ("ProShares Ultra Bloomberg Crude Oil", "commodity"),
        ("Direxion Daily Gold Bull 2X Shares", "commodity"),
        ("ProShares Bitcoin Strategy ETF", "commodity"),
        ("ProShares Short VIX Short-Term Futures ETF", "none"),  # volatility: no events
        ("ProShares VIX S&P 500 Futures", "none"),  # volatility before the index keyword
        ("Direxion Daily TSLA Bull 2X Shares", None),
    ],
)
def test_kind_from_the_keywords_of_the_name(name: str, kind: str | None) -> None:
    assert name_kind(name) == kind
