"""Yahoo analyst data (``YahooAnalyst``): price targets, annual consensus estimates and the
current recommendation counts of one name, from ONE ``quoteSummary`` request.

``quoteSummary/<SYM>?modules=financialData,earningsTrend,recommendationTrend`` answers
``quoteSummary.result[0]`` with ``financialData`` (``targetMeanPrice``, ``targetMedianPrice``,
``targetHighPrice``, ``targetLowPrice``, ``financialCurrency``), ``earningsTrend.trend[]``
(``period`` 0q / +1q / 0y / +1y, ``endDate`` the fiscal period end, ``earningsEstimate`` and
``revenueEstimate`` with ``avg``, ``numberOfAnalysts`` and the currency) and
``recommendationTrend.trend[]`` (``period`` 0m, -1m.., the five counts). Recorded 2026-10-22
(``tests/fixtures/sources/yahoo``): the request asks ``formatted=false``, and ``financialData``
numbers come bare while ``earningsTrend`` ones still come as ``{"raw": 1.5, "fmt": "1.5"}``, so a
number is read as either (an empty ``{}`` is missing). An unknown symbol answers 404
(``client.refused``); an ETF the same.

Request key: the symbol. ``normalize`` returns ``parsed["price_target"]``, ``["estimates_annual"]``
and ``["recommendation"]`` (a kind with nothing to store is an empty frame), shaped like the FMP
and Finnhub frames the snapshot task already turns into rows. Estimates keep the annual periods
(``0y``, ``+1y``) by their ``endDate`` (a period without one is dropped); which of them is the
forward year is the reader's job. Recommendation counts are the ``0m`` row, dated the first of the
session's month (Finnhub's convention).

Currency: the forward formulas assume USD, so a name whose estimates are not in USD stages no
estimate rows, and one whose ``financialCurrency`` is not USD (or missing) no targets, until the
formulas handle currency. Counts carry no currency and are kept.
"""

import json
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.http import Http
from algotrade_sources.vendors.yahoo.client import SOURCE, url

DATASET = "analyst"
USD = "USD"
ANNUAL = ("0y", "+1y")
TARGETS = {
    "targetMeanPrice": "target_consensus",
    "targetMedianPrice": "target_median",
    "targetHighPrice": "target_high",
    "targetLowPrice": "target_low",
}
COUNTS = {
    "strongBuy": "strong_buy",
    "buy": "buy",
    "hold": "hold",
    "sell": "sell",
    "strongSell": "strong_sell",
}
TARGET_COLUMNS = ["symbol", "target_high", "target_low", "target_consensus", "target_median"]
ESTIMATE_COLUMNS = [
    "symbol",
    "period",
    "fiscal_date",
    "eps_avg",
    "revenue_avg",
    "num_analysts_eps",
    "num_analysts_revenue",
    "currency",
]
RECOMMENDATION_COLUMNS = ["symbol", "period", *COUNTS.values()]


def number(value: Any) -> float | None:
    """A Yahoo number (``{"raw": x, "fmt": ".."}`` or a bare one) as a float; missing -> None."""
    if isinstance(value, dict):
        value = value.get("raw")
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def result(payload: bytes) -> dict[str, Any]:
    """``quoteSummary.result[0]``; no result is a ``ValueError`` (a 404 never gets here)."""
    data = json.loads(payload)
    found = ((data.get("quoteSummary") or {}).get("result") or [None])[0]
    if not isinstance(found, dict):
        raise ValueError(f"no quoteSummary result: {str(data)[:120]!r}")
    return found


def parse_targets(symbol: str, found: dict[str, Any]) -> pd.DataFrame:
    """One row of targets, or none when they are all missing or the name is not priced in USD."""
    data = found.get("financialData") or {}
    values = {ours: number(data.get(theirs)) for theirs, ours in TARGETS.items()}
    if data.get("financialCurrency") != USD or all(v is None for v in values.values()):
        return pd.DataFrame(columns=TARGET_COLUMNS)
    return pd.DataFrame([{"symbol": symbol, **values}])[TARGET_COLUMNS].astype(
        dict.fromkeys(TARGET_COLUMNS[1:], "float64")
    )


def parse_estimates(symbol: str, found: dict[str, Any]) -> pd.DataFrame:
    """The annual periods -> ``ESTIMATE_COLUMNS`` (``fiscal_date`` a UTC midnight); a period with
    no ``endDate``, or with a currency other than USD, is dropped."""
    out: list[dict[str, Any]] = []
    for trend in (found.get("earningsTrend") or {}).get("trend") or []:
        eps, revenue = trend.get("earningsEstimate") or {}, trend.get("revenueEstimate") or {}
        currencies = {eps.get("earningsCurrency"), revenue.get("revenueCurrency")} - {None}
        end = pd.to_datetime(trend.get("endDate"), utc=True, errors="coerce")
        if trend.get("period") not in ANNUAL or pd.isna(end) or currencies != {USD}:
            continue
        out.append(
            {
                "symbol": symbol,
                "period": "annual",
                "fiscal_date": end,
                "eps_avg": number(eps.get("avg")),
                "revenue_avg": number(revenue.get("avg")),
                "num_analysts_eps": number(eps.get("numberOfAnalysts")),
                "num_analysts_revenue": number(revenue.get("numberOfAnalysts")),
                "currency": USD,
            }
        )
    frame = pd.DataFrame(out, columns=ESTIMATE_COLUMNS)
    for col in ("num_analysts_eps", "num_analysts_revenue"):
        frame[col] = frame[col].astype("Int64")
    kept = frame.drop_duplicates("fiscal_date").sort_values("fiscal_date")
    return kept.reset_index(drop=True)


def parse_recommendation(symbol: str, found: dict[str, Any], session: date) -> pd.DataFrame:
    """The ``0m`` counts as one row dated the first of the session's month; none without it."""
    trend = (found.get("recommendationTrend") or {}).get("trend") or []
    current = [t for t in trend if t.get("period") == "0m"]
    if not current:
        return pd.DataFrame(columns=RECOMMENDATION_COLUMNS)
    month = pd.Timestamp(session.replace(day=1), tz="UTC")
    row: dict[str, Any] = {"symbol": symbol, "period": month}
    for theirs, ours in COUNTS.items():
        value = number(current[0].get(theirs))
        row[ours] = None if value is None else int(value)
    frame = pd.DataFrame([row], columns=RECOMMENDATION_COLUMNS)
    return frame.astype(dict.fromkeys(COUNTS.values(), "Int64"))


class YahooAnalyst:
    """Implements ``sources.base.Source``. Request key: the symbol."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``yahoo`` limiter (sources.toml)

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._http.get(url(request.key))

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        found = result(payload)
        symbol = request.key.strip().upper()
        session = request.session_date or datetime.now(UTC).date()
        parsed = {
            "price_target": parse_targets(symbol, found),
            "estimates_annual": parse_estimates(symbol, found),
            "recommendation": parse_recommendation(symbol, found, session),
        }
        return Normalized(request.session_date, {}, {}, parsed)
