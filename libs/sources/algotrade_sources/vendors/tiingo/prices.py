"""Tiingo daily prices for one ticker (``TiingoDailyPrices``).

``https://api.tiingo.com/tiingo/daily/{ticker}/prices?startDate=D1&endDate=D2&format=json``:
one request returns the whole window as a JSON list (``date``, ``open``, ``high``, ``low``,
``close``, ``volume``, the ``adj*`` twins, ``divCash``, ``splitFactor``). The key travels in an
``Authorization: Token`` header set on the transport, never in the URL. Free tier: 50 requests
an hour, 1,000 a day, 500 unique symbols a month, so every request waits on the shared
``tiingo`` limiter (``[tiingo] min_interval_s``, 72 s).

Bars are stored **unadjusted** (``open`` ... ``volume``, never the ``adj*`` fields): corporate
actions apply at read time (ADR 0016). ``splitFactor`` and ``divCash`` are kept in
``Normalized.parsed["actions"]`` for the task's split check, never stored from here.
"""

import json
from datetime import date
from urllib.parse import quote

import numpy as np
import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.http import Http

SOURCE = "tiingo"
DATASET = "daily_prices"
TABLE = "bars/1d"
HOST = "https://api.tiingo.com"
URL = HOST + "/tiingo/daily/{ticker}/prices?startDate={start}{end}&format=json"
DEFAULT_START = date(2018, 1, 1)  # the event-study history (ADR 0050)
BAR_COLUMNS = ("open", "high", "low", "close", "volume")
ACTION_COLUMNS = ("ts", "split_factor", "div_cash")


def vendor_ticker(symbol: str) -> str:
    """Our (ACT-style) symbol -> Tiingo's: a share class is written with a hyphen (``BRK.B`` ->
    ``BRK-B``)."""
    return symbol.strip().upper().replace(".", "-")


def parse_key(key: str) -> tuple[str, date, date | None]:
    """``TICKER`` or ``TICKER:START:END`` (ISO dates; an empty END is open) -> ticker, start,
    end. A bare ticker asks for everything since ``DEFAULT_START``."""
    ticker, _, window = key.partition(":")
    start_text, _, end_text = window.partition(":")
    start = date.fromisoformat(start_text) if start_text else DEFAULT_START
    return ticker, start, date.fromisoformat(end_text) if end_text else None


def parse_prices(payload: bytes) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """-> (unadjusted bars: ``ts`` + ``BAR_COLUMNS``, split / dividend days: ``ACTION_COLUMNS``,
    invalid rows dropped). ``ts`` is midnight UTC of the session date."""
    rows = json.loads(payload)
    if not isinstance(rows, list):
        raise ValueError(f"expected a JSON list of daily prices, got {str(rows)[:120]!r}")
    frame = pd.DataFrame(rows, columns=["date", *BAR_COLUMNS, "divCash", "splitFactor"])
    if frame.empty:
        return pd.DataFrame(columns=["ts", *BAR_COLUMNS]), pd.DataFrame(columns=ACTION_COLUMNS), 0
    days = pd.to_datetime(frame["date"].astype(str).str[:10], utc=True)
    values = frame[list(BAR_COLUMNS)].apply(pd.to_numeric, errors="coerce").astype(float)
    o, h, low, c, v = (values[k].to_numpy() for k in BAR_COLUMNS)
    valid = (
        np.isfinite(o)
        & np.isfinite(h)
        & np.isfinite(low)
        & np.isfinite(c)
        & (np.nan_to_num(v, nan=-1.0) >= 0)
        & (np.minimum.reduce([o, h, low, c]) > 0)
        & (h >= np.maximum(o, c))
        & (low <= np.minimum(o, c))
    )
    bars = values.assign(ts=days)[valid].drop_duplicates("ts", keep="last")
    split = pd.to_numeric(frame["splitFactor"], errors="coerce").fillna(1.0)
    cash = pd.to_numeric(frame["divCash"], errors="coerce").fillna(0.0)
    actions = pd.DataFrame({"ts": days, "split_factor": split, "div_cash": cash})
    actions = actions[(actions["split_factor"] != 1.0) | (actions["div_cash"] != 0.0)]
    return (
        bars[["ts", *BAR_COLUMNS]].sort_values("ts").reset_index(drop=True),
        actions.drop_duplicates("ts", keep="last").sort_values("ts").reset_index(drop=True),
        int((~valid).sum()),
    )


class TiingoDailyPrices:
    """Implements ``sources.base.Source``. Request key: the ticker, optionally with its window
    (``AAPL:2018-01-01:2026-10-05``); ``instrument_id`` (when given) keys the rows."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``tiingo`` limiter (sources.toml)

    def fetch(self, request: FetchRequest) -> bytes | None:
        ticker, start, end = parse_key(request.key)
        until = "" if end is None else f"&endDate={end.isoformat()}"
        url = URL.format(
            ticker=quote(vendor_ticker(ticker), safe="-"), start=start.isoformat(), end=until
        )
        return self._http.get(url)  # a ticker Tiingo does not know answers 404: None

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        ticker = parse_key(request.key)[0].strip().upper()
        bars, actions, invalid = parse_prices(payload)
        bars = bars.assign(symbol=ticker)
        if request.instrument_id:
            bars = bars.assign(instrument_id=request.instrument_id)
        return Normalized(
            session_date=None,  # a history: every row carries its own ``ts``
            tables={TABLE: bars},
            notes={"invalid_rows": invalid},
            parsed={"actions": actions},
        )
