"""Massive unadjusted daily bars for the whole market (``MassiveDailyBars``).

Grouped daily ``/v2/aggs/grouped/locale/us/market/stocks/{date}?adjusted=false``: one request
returns every US stock and ETF for a session (free tier: 2 years of history). Bars are stored
**unadjusted**; corporate actions are applied at read time (ADR 0016).
"""

import json
from datetime import date

import numpy as np
import pandas as pd

from algotrade_ingestion.sources.framework.base import FetchRequest, Normalized
from algotrade_ingestion.sources.vendors.massive.client import HOST, _Massive, act_symbol

GROUPED = HOST + "/v2/aggs/grouped/locale/us/market/stocks/{date}?adjusted=false&include_otc=false"


def parse_grouped(day: date, payload: bytes) -> tuple[pd.DataFrame, int]:
    """-> (``bars/1d`` rows keyed by ``symbol``, invalid rows dropped). Empty on holidays."""
    results = json.loads(payload).get("results") or []
    frame = pd.DataFrame(results, columns=["T", "o", "h", "l", "c", "v", "vw", "t", "n"])
    columns = ["symbol", "ts", "open", "high", "low", "close", "volume", "vwap", "trades"]
    if frame.empty:
        return pd.DataFrame(columns=columns), 0
    bars = pd.DataFrame(
        {
            "symbol": [act_symbol(str(t)) for t in frame["T"]],
            "ts": pd.to_datetime(frame["t"], unit="ms", utc=True),
            "open": frame["o"],
            "high": frame["h"],
            "low": frame["l"],
            "close": frame["c"],
            "volume": frame["v"],
            "vwap": frame["vw"],
            "trades": frame["n"],
        }
    ).astype({"open": float, "high": float, "low": float, "close": float, "volume": float})
    o, h, low, c, v = (bars[k].to_numpy() for k in ("open", "high", "low", "close", "volume"))
    valid = (
        np.isfinite(o)
        & np.isfinite(h)
        & np.isfinite(low)
        & np.isfinite(c)
        & (np.nan_to_num(v) >= 0)
        & (np.minimum.reduce([o, h, low, c]) > 0)
        & (h >= np.maximum(o, c))
        & (low <= np.minimum(o, c))
    )
    bars = bars[valid].drop_duplicates("symbol", keep="last")
    return bars.sort_values("symbol").reset_index(drop=True), int((~valid).sum())


class MassiveDailyBars(_Massive):
    """Request key: the session date (ISO)."""

    dataset = "grouped_daily"

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._get(GROUPED.format(date=date.fromisoformat(request.key).isoformat()))

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        day = date.fromisoformat(request.key)
        bars, invalid = parse_grouped(day, payload)
        return Normalized(
            session_date=day, tables={"bars/1d": bars}, notes={"invalid_rows": invalid}
        )
