"""SPY daily holdings (State Street): S&P 500 membership as data.

The file is an Excel workbook: a few header lines ("Holdings: As of 01-Oct-2026"), a table
(Name, Ticker, Identifier, SEDOL, Weight, Sector, Shares Held, Local Currency) and then
disclaimer text. Tickers use the same style as Nasdaq Trader (``BRK.B``). Non-security lines
(cash ``-``, identifiers that are not tickers) are skipped and counted.
"""

from datetime import date

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.holdings import holding_ticker
from algotrade_sources.framework.http import Http
from algotrade_sources.vendors.ssga.workbook import read_workbook

SOURCE = "ssga_spy"
DATASET = "spy_holdings"
URL = "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx"


def parse_holdings(payload: bytes) -> tuple[pd.DataFrame, date | None, int]:
    """-> (holdings with ``symbol``, ``name``, ``weight``; the as-of date; skipped lines)."""
    book = read_workbook(payload)
    if "Ticker" not in book.table.columns:
        raise ValueError("SPY holdings workbook has no Name / Ticker table")
    holdings, skipped = [], 0
    for name, ticker, weight in zip(
        book.table["Name"], book.table["Ticker"], book.table["Weight"], strict=True
    ):
        symbol = holding_ticker(ticker)  # a blank cell is not the ticker "NAN"
        if symbol is None:
            skipped += 1
            continue
        holdings.append({"symbol": symbol, "name": name, "weight": float(weight or 0.0)})
    return pd.DataFrame(holdings, columns=["symbol", "name", "weight"]), book.as_of, skipped


class SpyHoldingsSource:
    """Implements ``sources.base.Source``. Request key: ``SPY``."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._http.get(URL)

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        holdings, as_of, skipped = parse_holdings(payload)
        if holdings.empty:
            return None
        return Normalized(
            session_date=as_of,
            tables={},
            notes={"skipped_lines": skipped},
            parsed={"sp500": holdings},
        )
