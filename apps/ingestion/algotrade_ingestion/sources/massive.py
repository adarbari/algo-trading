"""Massive (formerly Polygon) REST: unadjusted daily bars for the whole market, splits, dividends.

- grouped daily ``/v2/aggs/grouped/locale/us/market/stocks/{date}?adjusted=false``: one request
  returns every US stock and ETF for a session (free tier: 2 years of history).
- splits ``/stocks/v1/splits``, dividends ``/stocks/v1/dividends``: filtered by date, paginated
  through ``next_url``.

The API key travels in an ``Authorization`` header (set on the transport), never in URLs, so it
cannot leak into logs or the raw store. Free tier: 5 requests/minute, so every request waits on
a ``MinInterval`` (default 12.5 s). Bars are stored **unadjusted**; corporate actions are applied
at read time (ADR 0016).
"""

import json
import re
from datetime import UTC, date, datetime
from typing import Any

import numpy as np
import pandas as pd

from algotrade.core.instruments import AssetClass, instrument_id
from algotrade.storage.schemas import BAR_COLUMNS
from algotrade_ingestion.sources.base import FetchRequest, Normalized
from algotrade_ingestion.sources.http import (
    MinInterval,
    RetryPolicy,
    Sleep,
    Transport,
    get_with_retry,
)

SOURCE = "massive"
HOST = "https://api.massive.com"
GROUPED = HOST + "/v2/aggs/grouped/locale/us/market/stocks/{date}?adjusted=false&include_otc=false"
SPLITS = HOST + "/stocks/v1/splits?execution_date.gte={start}&execution_date.lte={end}&limit=5000"
TICKERS = HOST + "/v3/reference/tickers?market=stocks&active=true&limit=1000"
DIVIDENDS = (
    HOST + "/stocks/v1/dividends?ex_dividend_date.gte={start}&ex_dividend_date.lte={end}&limit=5000"
)
FREE_TIER_INTERVAL_S = 12.5
_PREFERRED = re.compile(r"^([A-Z]+)p([A-Z]*)$")  # Massive "KIMpL" == ACT "KIM$L"


def act_symbol(ticker: str) -> str:
    """Massive ticker -> the ACT-style symbol used by the universe (``KIMpL`` -> ``KIM$L``)."""
    match = _PREFERRED.match(ticker)
    return f"{match.group(1)}${match.group(2)}" if match else ticker.upper()


def _ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(date.fromisoformat(value), tz="UTC")


def parse_grouped(day: date, payload: bytes) -> tuple[pd.DataFrame, int]:
    """-> (``bars/1d`` rows for the session, invalid rows dropped). Empty on holidays."""
    results = json.loads(payload).get("results") or []
    frame = pd.DataFrame(results, columns=["T", "o", "h", "l", "c", "v", "vw", "t", "n"])
    if frame.empty:
        return pd.DataFrame(columns=[*BAR_COLUMNS, "vwap", "trades"]), 0
    bars = pd.DataFrame(
        {
            "instrument_id": [
                instrument_id(AssetClass.EQUITY, act_symbol(str(t))) for t in frame["T"]
            ],
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
    bars = bars[valid].drop_duplicates("instrument_id", keep="last")
    return bars.sort_values("instrument_id").reset_index(drop=True), int((~valid).sum())


def parse_splits(results: list[dict[str, Any]]) -> pd.DataFrame:
    rows = [
        {
            "instrument_id": instrument_id(AssetClass.EQUITY, act_symbol(str(r["ticker"]))),
            "ts": _ts(r["execution_date"]),
            "symbol": act_symbol(str(r["ticker"])),
            "split_from": float(r["split_from"]),
            "split_to": float(r["split_to"]),
            "ratio": float(r["split_to"]) / float(r["split_from"]),
            "adjustment_type": r.get("adjustment_type"),
        }
        for r in results
        if r.get("ticker") and r.get("split_from") and r.get("split_to")
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "instrument_id",
            "ts",
            "symbol",
            "split_from",
            "split_to",
            "ratio",
            "adjustment_type",
        ],
    ).drop_duplicates(["instrument_id", "ts"])


def parse_dividends(results: list[dict[str, Any]]) -> pd.DataFrame:
    rows = [
        {
            "instrument_id": instrument_id(AssetClass.EQUITY, act_symbol(str(r["ticker"]))),
            "ts": _ts(r["ex_dividend_date"]),
            "symbol": act_symbol(str(r["ticker"])),
            "cash_amount": float(r["cash_amount"]),
            "currency": r.get("currency"),
            "pay_date": r.get("pay_date"),
            "record_date": r.get("record_date"),
            "declaration_date": r.get("declaration_date"),
            "frequency": r.get("frequency"),
            "distribution_type": r.get("distribution_type"),
        }
        for r in results
        if r.get("ticker") and r.get("ex_dividend_date") and r.get("cash_amount")
    ]
    columns = [
        "instrument_id",
        "ts",
        "symbol",
        "cash_amount",
        "currency",
        "pay_date",
        "record_date",
        "declaration_date",
        "frequency",
        "distribution_type",
    ]
    # Several distributions can share an ex-date (special + regular): keep them all, summed.
    frame = pd.DataFrame(rows, columns=columns)
    if frame.empty:
        return frame
    return (
        frame.groupby(["instrument_id", "ts"], as_index=False).agg(
            {**dict.fromkeys(columns[2:], "first"), "cash_amount": "sum"}
        )
    )[columns]


class _Massive:
    name = SOURCE
    dataset = "massive"

    def __init__(
        self,
        transport: Transport,
        sleep: Sleep,
        policy: RetryPolicy | None = None,
        min_interval_s: float = FREE_TIER_INTERVAL_S,
    ) -> None:
        self._transport, self._sleep, self._policy = transport, sleep, policy or RetryPolicy()
        self._pace = MinInterval(min_interval_s, sleep)

    def _get(self, url: str) -> bytes | None:
        self._pace.wait()
        return get_with_retry(self._transport, url, self._policy, self._sleep)

    def _paged(self, url: str) -> bytes | None:
        """Follow ``next_url`` and return one JSON document holding every page's results."""
        results: list[Any] = []
        next_url: str | None = url
        while next_url:
            body = self._get(next_url)
            if body is None:
                return None
            doc = json.loads(body)
            results.extend(doc.get("results") or [])
            next_url = doc.get("next_url")
        return json.dumps(
            {"results": results, "fetched_at": datetime.now(UTC).isoformat()}
        ).encode()


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


class MassiveCorporateActions(_Massive):
    """Request key: ``splits:<start>:<end>`` or ``dividends:<start>:<end>`` (ISO dates)."""

    dataset = "corporate_actions"

    def fetch(self, request: FetchRequest) -> bytes | None:
        kind, start, end = request.key.split(":")
        template = {"splits": SPLITS, "dividends": DIVIDENDS}[kind]
        return self._paged(template.format(start=start, end=end))

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        kind = request.key.split(":")[0]
        results = json.loads(payload).get("results") or []
        table, frame = (
            ("events/split", parse_splits(results))
            if kind == "splits"
            else ("events/dividend", parse_dividends(results))
        )
        return Normalized(session_date=None, tables={table: frame})


# Massive security types -> ours. Unknown codes stay None (our name rules decide).
MASSIVE_TYPES = {
    "CS": "COMMON_STOCK",
    "OS": "COMMON_STOCK",
    "ADRC": "ADR",
    "ADRP": "PREFERRED",
    "ADRW": "WARRANT",
    "ADRR": "RIGHT",
    "GDR": "ADR",
    "ETF": "ETF",
    "ETN": "ETN",
    "ETV": "ETF",
    "ETS": "ETF",
    "PFD": "PREFERRED",
    "WARRANT": "WARRANT",
    "RIGHT": "RIGHT",
    "UNIT": "UNIT",
    "SP": "NOTE",
    "BOND": "NOTE",
    "BASKET": "ETF",
    "FUND": "CEF",
    "LT": "COMMON_STOCK",
}


def parse_tickers(results: list[dict[str, Any]]) -> pd.DataFrame:
    """Massive ticker list -> identifiers and vendor type per ACT symbol."""
    rows = [
        {
            "symbol": act_symbol(str(r["ticker"])),
            "figi": r.get("composite_figi") or None,
            "share_class_figi": r.get("share_class_figi") or None,
            "cik": r.get("cik") or None,
            "vendor_type": r.get("type") or None,
            "vendor_security_type": MASSIVE_TYPES.get(str(r.get("type"))),
        }
        for r in results
        if r.get("ticker")
    ]
    columns = ["symbol", "figi", "share_class_figi", "cik", "vendor_type", "vendor_security_type"]
    return pd.DataFrame(rows, columns=columns).drop_duplicates("symbol", keep="first")


class MassiveTickers(_Massive):
    """Every active US stock/ETF ticker with FIGI, CIK and type. Request key: ``active``."""

    dataset = "tickers"

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._paged(TICKERS)

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        frame = parse_tickers(json.loads(payload).get("results") or [])
        return (
            None
            if frame.empty
            else Normalized(session_date=None, tables={}, parsed={"tickers": frame})
        )
