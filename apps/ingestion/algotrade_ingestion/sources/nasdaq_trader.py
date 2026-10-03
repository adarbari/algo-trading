"""Nasdaq Trader symbol directory: every US-listed security, plus which have listed options.

Files (pipe-delimited, last line "File Creation Time: ..."), updated through the trading day:
- ``nasdaqlisted``: Nasdaq-listed securities (Symbol, Security Name, Market Category, Test
  Issue, Financial Status, Round Lot Size, ETF, NextShares)
- ``otherlisted``:  NYSE / NYSE American / NYSE Arca / Cboe / IEX listings (ACT Symbol,
  Security Name, Exchange, CQS Symbol, ETF, Round Lot Size, Test Issue, NASDAQ Symbol)
- ``options``:      every listed option series; only the distinct underlyings are kept

Official and free. Symbols use ACT style (``BRK.B``, ``ABR$D``), the same as SPY holdings.
"""

import io

import pandas as pd

from algotrade_ingestion.sources.base import FetchRequest, Normalized
from algotrade_ingestion.sources.http import RetryPolicy, Sleep, Transport, get_with_retry

SOURCE = "nasdaq_trader"
DATASET = "symbol_directory"
URL = "https://www.nasdaqtrader.com/dynamic/SymDir/{file}.txt"
FILES = ("nasdaqlisted", "otherlisted", "options")
EXCHANGES = {"A": "NYSE_AMERICAN", "N": "NYSE", "P": "NYSE_ARCA", "Z": "CBOE_BZX", "V": "IEX"}
LISTINGS = (
    "symbol",
    "name",
    "exchange",
    "is_etf",
    "is_test_issue",
    "round_lot",
    "financial_status",
)


def _read(payload: bytes) -> pd.DataFrame:
    frame = pd.read_csv(io.BytesIO(payload), sep="|", dtype=str, keep_default_na=False)
    first = frame.columns[0]
    return frame[~frame[first].str.startswith("File Creation Time")].reset_index(drop=True)


def _flag(series: pd.Series) -> pd.Series:
    return series.str.strip().str.upper().eq("Y")


def parse_listings(file: str, payload: bytes) -> pd.DataFrame:
    """``nasdaqlisted`` / ``otherlisted`` -> one row per listed symbol (``LISTINGS`` columns)."""
    raw = _read(payload)
    if file == "nasdaqlisted":
        symbol, exchange, status = (
            raw["Symbol"],
            pd.Series("NASDAQ", index=raw.index),
            raw["Financial Status"],
        )
    else:
        symbol = raw["ACT Symbol"]
        exchange = raw["Exchange"].map(lambda code: EXCHANGES.get(code, code or "UNKNOWN"))
        status = pd.Series("", index=raw.index)
    out = pd.DataFrame(
        {
            "symbol": symbol.str.strip().str.upper(),
            "name": raw["Security Name"].str.strip(),
            "exchange": exchange,
            "is_etf": _flag(raw["ETF"]),
            "is_test_issue": _flag(raw["Test Issue"]),
            "round_lot": pd.to_numeric(raw["Round Lot Size"], errors="coerce"),
            "financial_status": status.str.strip(),
        }
    )
    return out[out["symbol"] != ""].reset_index(drop=True)


def parse_option_underlyings(payload: bytes) -> pd.DataFrame:
    """``options`` -> the distinct underlying symbols with listed options."""
    raw = _read(payload)
    symbols = raw["Underlying Symbol"].str.strip().str.upper()
    return pd.DataFrame({"symbol": sorted(set(symbols[symbols != ""]))})


class NasdaqTraderSource:
    """Implements ``sources.base.Source``. Request key: one of ``FILES``."""

    name = SOURCE
    dataset = DATASET

    def __init__(
        self, transport: Transport, sleep: Sleep, policy: RetryPolicy | None = None
    ) -> None:
        self._transport, self._sleep, self._policy = transport, sleep, policy or RetryPolicy()

    def fetch(self, request: FetchRequest) -> bytes | None:
        if request.key not in FILES:
            raise ValueError(f"unknown Nasdaq Trader file {request.key!r}; expected {FILES}")
        return get_with_retry(
            self._transport, URL.format(file=request.key), self._policy, self._sleep
        )

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        if request.key == "options":
            parsed = parse_option_underlyings(payload)
        else:
            parsed = parse_listings(request.key, payload)
        if parsed.empty:
            return None
        return Normalized(session_date=None, tables={}, parsed={request.key: parsed})
