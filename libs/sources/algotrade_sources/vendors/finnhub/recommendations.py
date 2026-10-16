"""Finnhub analyst recommendation trends (``FinnhubRecommendations``).

``/api/v1/stock/recommendation?symbol=S`` answers one record per month, newest first: ``symbol``,
``period`` (the first of the month, ISO date) and the analyst counts ``strongBuy``, ``buy``,
``hold``, ``sell``, ``strongSell`` (verified 2026-10-16 on a free key). An unknown symbol answers
``[]``.

Request key: the symbol. ``normalize`` returns ``parsed["recommendations"]``
(``RECOMMENDATION_COLUMNS``, ``period`` a UTC midnight): nothing is stored from here yet; the
history of the trend starts at the first fetch (ADR 0068).
"""

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.http import Http
from algotrade_sources.vendors.finnhub.client import SOURCE, rows, url, vendor_symbol

DATASET = "recommendations"
COUNTS = {
    "strongBuy": "strong_buy",
    "buy": "buy",
    "hold": "hold",
    "sell": "sell",
    "strongSell": "strong_sell",
}
RECOMMENDATION_COLUMNS = ["symbol", "period", *COUNTS.values()]


def parse_recommendations(payload: bytes) -> pd.DataFrame:
    """The records -> ``RECOMMENDATION_COLUMNS``, oldest month first; a record with no symbol
    or period is dropped, a repeated (symbol, period) kept once."""
    records = rows(payload)
    periods = pd.Series([r.get("period") for r in records])
    frame = pd.DataFrame(
        {
            "symbol": [str(r.get("symbol") or "").strip().upper() for r in records],
            "period": pd.to_datetime(periods, utc=True, errors="coerce"),
        }
    )
    for theirs, ours in COUNTS.items():
        frame[ours] = pd.array([r.get(theirs) for r in records], dtype="Int64")
    kept = frame[(frame["symbol"] != "") & frame["period"].notna()]
    ordered = kept.drop_duplicates(["symbol", "period"]).sort_values("period")
    return ordered[RECOMMENDATION_COLUMNS].reset_index(drop=True)


class FinnhubRecommendations:
    """Implements ``sources.base.Source``. Request key: the symbol."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``finnhub`` limiter (sources.toml)

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._http.get(url("stock/recommendation", symbol=vendor_symbol(request.key)))

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        parsed = {"recommendations": parse_recommendations(payload)}
        return Normalized(request.session_date, {}, {}, parsed)
