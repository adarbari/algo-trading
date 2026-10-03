"""SPY daily holdings (State Street): S&P 500 membership as data.

The file is an Excel workbook: a few header lines ("Holdings: As of 01-Oct-2026"), a table
(Name, Ticker, Identifier, SEDOL, Weight, Sector, Shares Held, Local Currency) and then
disclaimer text. Tickers use the same style as Nasdaq Trader (``BRK.B``). Non-security lines
(cash ``-``, identifiers that are not tickers) are skipped and counted.
"""

import io
import re
from datetime import date, datetime

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.http import Http

SOURCE = "ssga_spy"
DATASET = "spy_holdings"
URL = "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx"
_TICKER = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")
_AS_OF = re.compile(r"As of (\d{2}-[A-Za-z]{3}-\d{4})")


def parse_holdings(payload: bytes) -> tuple[pd.DataFrame, date | None, int]:
    """-> (holdings with ``symbol``, ``name``, ``weight``; the as-of date; skipped lines)."""
    import openpyxl  # noqa: PLC0415 - algotrade-sources-only dependency, loaded where needed

    sheet = openpyxl.load_workbook(io.BytesIO(payload), read_only=True, data_only=True).active
    rows = [r for r in sheet.iter_rows(values_only=True) if any(v is not None for v in r)]
    as_of = None
    for row in rows[:6]:
        match = _AS_OF.search(" ".join(str(v) for v in row if v))
        if match:
            as_of = datetime.strptime(match.group(1), "%d-%b-%Y").date()  # noqa: DTZ007
    header = next(i for i, r in enumerate(rows) if r[0] == "Name" and r[1] == "Ticker")
    holdings, skipped = [], 0
    for row in rows[header + 1 :]:
        if row[1] is None:  # disclaimer text after the table
            break
        ticker = str(row[1]).strip().upper()
        if not _TICKER.match(ticker):
            skipped += 1
            continue
        holdings.append({"symbol": ticker, "name": row[0], "weight": float(row[4] or 0.0)})
    return pd.DataFrame(holdings, columns=["symbol", "name", "weight"]), as_of, skipped


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
