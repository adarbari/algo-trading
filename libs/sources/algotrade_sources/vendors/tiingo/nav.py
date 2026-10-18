"""Tiingo's NAV series of closed-end funds: the Nasdaq Mutual Fund Quotation Service symbols
``X<ticker>X`` (``TiingoNavTickers``, ``TiingoFundNav``; edge build D5).

A closed-end fund of $75 M or more reports a NAV per share to Nasdaq's MFQS every evening under
the symbol ``X<ticker>X`` (``PHK`` -> ``XPHKX``). Tiingo carries those symbols as end-of-day
series, so a fund's NAV history is the same request as a stock's bars
(``/tiingo/daily/XPHKX/prices``), at the same pace and under the same licence.

- ``TiingoNavTickers`` reads the supported-tickers file (the one ``listings.py`` parses) and
  keeps the rows of exchange ``NMFQS`` (``ticker``, ``asset_type``, ``first_nav``,
  ``last_nav``): the NAV symbols Tiingo actually has. The file also lists ~49,800 ordinary
  mutual funds under that exchange, so a symbol built from a ticker is a NAV symbol only
  when the task's mapper has also matched the fund (a collision such as ``XCATX`` for ``CAT``
  is a real fund, not Caterpillar's NAV).
- ``TiingoFundNav`` fetches one symbol's window (key ``XPHKX:2004-01-01:2026-10-16``, the
  ``prices`` key) and keeps ``ts`` (midnight UTC of the NAV date) and ``nav`` (the unadjusted
  ``close``: a fund's ``adjClose`` folds its distributions in, and a premium or discount is
  the market price over the NAV as struck). Volume and the other price fields are not read: a
  NAV series has no volume and ``open == high == low == close`` where they are present.
  Rows with a missing or non-positive close are dropped and counted (``invalid_rows``); a
  repeated date keeps the last row.
"""

import json
from urllib.parse import quote

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.http import Http
from algotrade_sources.vendors.tiingo.listings import URL as LISTINGS_URL
from algotrade_sources.vendors.tiingo.listings import read_listing_csv
from algotrade_sources.vendors.tiingo.prices import SOURCE, URL, parse_key, vendor_ticker

TICKERS_DATASET = "nav_tickers"
NAV_DATASET = "fund_nav"
TABLE = "events/fund_nav"
NAV_EXCHANGE = "NMFQS"
NAV_TICKER_COLUMNS = ["ticker", "asset_type", "first_nav", "last_nav"]
NAV_COLUMNS = ["ts", "nav"]


def parse_nav_tickers(payload: bytes) -> pd.DataFrame:
    """The supported-tickers ZIP (or CSV) -> the ``NMFQS`` rows (``NAV_TICKER_COLUMNS``), one
    per ticker; ``last_nav`` (None when blank) is the last day Tiingo has the series: the day
    before the file's for a live one, as NAVs arrive a day late (a window is clipped to it)."""
    raw = read_listing_csv(payload)
    ticker = raw["ticker"].str.strip().str.upper()
    start = pd.to_datetime(raw["startDate"].str.strip(), errors="coerce")
    end = pd.to_datetime(raw["endDate"].str.strip(), errors="coerce")
    mine = raw["exchange"].str.strip().str.upper().eq(NAV_EXCHANGE) & (ticker != "")
    mine &= raw["priceCurrency"].str.strip().str.upper().eq("USD") & start.notna()
    out = pd.DataFrame(
        {
            "ticker": ticker,
            "asset_type": raw["assetType"].str.strip(),
            "first_nav": start.dt.date,
            "last_nav": end.dt.date,
        }
    )[mine]
    out["last_nav"] = out["last_nav"].astype(object).where(out["last_nav"].notna(), None)
    out = out.sort_values(["ticker", "first_nav"], kind="stable")
    return out.drop_duplicates("ticker", keep="last").reset_index(drop=True)[NAV_TICKER_COLUMNS]


def parse_nav(payload: bytes) -> tuple[pd.DataFrame, int]:
    """One symbol's ``prices`` JSON -> (``NAV_COLUMNS`` rows by date, invalid rows dropped)."""
    rows = json.loads(payload)
    if not isinstance(rows, list):
        raise ValueError(f"expected a JSON list of daily prices, got {str(rows)[:120]!r}")
    frame = pd.DataFrame(rows, columns=["date", "close"])
    if frame.empty:
        return pd.DataFrame(columns=NAV_COLUMNS), 0
    nav = pd.to_numeric(frame["close"], errors="coerce").astype(float)
    valid = nav.notna() & (nav > 0) & (nav < float("inf"))
    days = pd.to_datetime(frame["date"].astype(str).str[:10], utc=True)
    out = pd.DataFrame({"ts": days, "nav": nav})[valid]
    out = out.drop_duplicates("ts", keep="last").sort_values("ts").reset_index(drop=True)
    return out, int((~valid).sum())


class TiingoNavTickers:
    """Implements ``sources.base.Source``. The request key is ignored (one file, one request)."""

    name = SOURCE
    dataset = TICKERS_DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``tiingo`` limiter (sources.toml)

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._http.get(LISTINGS_URL)

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        return Normalized(
            session_date=request.session_date,
            tables={},
            parsed={"nav_tickers": parse_nav_tickers(payload)},
        )


class TiingoFundNav:
    """Implements ``sources.base.Source``. Request key: the NAV symbol with its window
    (``XPHKX:2004-01-01:2026-10-16``); ``instrument_id`` keys the rows."""

    name = SOURCE
    dataset = NAV_DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``tiingo`` limiter (sources.toml)

    def fetch(self, request: FetchRequest) -> bytes | None:
        symbol, start, end = parse_key(request.key)
        until = "" if end is None else f"&endDate={end.isoformat()}"
        url = URL.format(
            ticker=quote(vendor_ticker(symbol), safe="-"), start=start.isoformat(), end=until
        )
        return self._http.get(url)  # a symbol Tiingo does not know answers 404: None

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        symbol = parse_key(request.key)[0].strip().upper()
        nav, invalid = parse_nav(payload)
        nav = nav.assign(series="nav", nav_symbol=symbol)
        if request.instrument_id:
            nav = nav.assign(instrument_id=request.instrument_id)
        return Normalized(session_date=None, tables={TABLE: nav}, notes={"invalid_rows": invalid})
