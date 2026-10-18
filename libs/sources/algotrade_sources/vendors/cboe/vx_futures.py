"""Cboe VIX futures (VX) by expiry: one CSV per contract from Cboe's CDN, no key.

``https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/VX_<expiry>.csv``
(static S3 objects; history from 2013, an expiry that never existed answers 403 with S3's
``AccessDenied`` XML, which the source registry treats as "no such file"). One file holds the
whole life of ONE contract, one row per trade date: ``Trade Date,Futures,Open,High,Low,Close,
Settle,Change,Total Volume,EFP,Open Interest`` (``Trade Date`` ISO, prices in index points).

Measured 2026-10-17 (docs/data/vendors.md): ``Futures`` is the CONTRACT MONTH label (``F (Jan
2025)``), the same for the Wednesday weeklies of that month, so the expiry is the file's own
date, never the label; before 2013-05-20 the settlement column is ``0`` (Cboe did not publish
one) and a day without a trade has ``0.0000`` open, high, low and close with a settle. A
zero is not a price: ``normalize`` stores it null. The file of an expiry is last modified
about 01:05 New York time on the day AFTER the trade date, so the row of a session is in no
file before the next morning (the task's ``knowledge_ts`` is its fetch instant).

Which expiries exist (the directory cannot be listed) is the task's rule
(``tasks/market/volatility/vx_futures.py``); this module reads one file.
"""

from datetime import date
from io import BytesIO

import pandas as pd

from algotrade.core.model.instruments import AssetClass, instrument_id
from algotrade_sources.framework.base import FetchRequest, Normalized, TransientFetchError
from algotrade_sources.framework.http import Http

SOURCE = "cboe_vx"
DATASET = "vx_futures_file"
TABLE = "volatility/vx_futures"
URL = "https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/VX_{expiry}.csv"
ROOT = "VX"
FILE_COLUMNS = (
    "Trade Date", "Futures", "Open", "High", "Low", "Close", "Settle", "Change",
    "Total Volume", "EFP", "Open Interest",
)  # fmt: skip
PRICES = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Settle": "settle"}
COUNTS = {"Total Volume": "volume", "EFP": "efp", "Open Interest": "open_interest"}
COLUMNS = (
    "instrument_id", "root", "expiry", "contract", "session_date",
    "open", "high", "low", "close", "settle", "change", "volume", "efp", "open_interest",
)  # fmt: skip
PREVIEW = 80


def contract_id(expiry: date) -> str:
    """``FUT:VX-20250122``: the contract that settles on ``expiry``."""
    return instrument_id(AssetClass.FUTURE, f"{ROOT}-{expiry:%Y%m%d}")


def _refused(expiry: date, why: str, payload: bytes) -> TransientFetchError:
    head = payload.decode("utf-8", errors="replace").strip()[:PREVIEW]
    return TransientFetchError(f"VX {expiry}: {why}; the body starts {head!r}")


def parse_vx(expiry: date, payload: bytes) -> pd.DataFrame:
    """The ``COLUMNS`` rows of one contract's file: a zero price is null, a row whose trade
    date does not read is dropped. A body that is not the table raises
    ``TransientFetchError`` (an HTML block page is never an empty contract)."""
    if payload.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<"):
        raise _refused(expiry, "an HTML page, not the table", payload)
    try:
        raw = pd.read_csv(BytesIO(payload), dtype=str, encoding="utf-8-sig")
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
        raise _refused(expiry, f"not a CSV table ({exc})", payload) from exc
    raw.columns = [str(c).strip() for c in raw.columns]
    missing = [c for c in FILE_COLUMNS if c not in raw.columns]
    if missing:
        raise _refused(expiry, f"no column {missing} in the file", payload)
    days = pd.to_datetime(raw["Trade Date"], format="%Y-%m-%d", errors="coerce")
    raw = raw[days.notna()].reset_index(drop=True)
    frame = pd.DataFrame(
        {
            "instrument_id": contract_id(expiry),
            "root": ROOT,
            "expiry": expiry,
            "contract": raw["Futures"].str.strip(),
            "session_date": days[days.notna()].dt.date.to_numpy(),
        }
    )
    for column, name in PRICES.items():
        values = pd.to_numeric(raw[column], errors="coerce").astype("float64")
        frame[name] = values.where(values > 0)
    frame["change"] = pd.to_numeric(raw["Change"], errors="coerce").astype("float64")
    for column, name in COUNTS.items():
        frame[name] = pd.to_numeric(raw[column], errors="coerce").astype("Int64")
    return frame.sort_values("session_date", kind="stable").reset_index(drop=True)[list(COLUMNS)]


class CboeVxFutures:
    """Implements ``sources.base.Source``. Request key: the expiry, ISO (``"2025-01-22"``)."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``cboe_vx`` limiter (sources.toml)

    def fetch(self, request: FetchRequest) -> bytes | None:
        expiry = date.fromisoformat(request.key)
        return self._http.get(URL.format(expiry=expiry.isoformat()))

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        frame = parse_vx(date.fromisoformat(request.key), payload)
        return Normalized(session_date=None, tables={TABLE: frame})
