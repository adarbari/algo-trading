"""Massive ticker details as of a day: what a ticker was then (``MassiveTickerDetails``).

``GET /v3/reference/tickers/{ticker}?date=D`` answers the record as it stood on ``D`` (ADR 0087,
PR3b): probed 2026-11-01, ``BBBY`` on 2023-05-02 is the old Bed Bath & Beyond (``list_date``
1992-06-04), not the company that reused the ticker later. The task asks at a delisted record's
last trading day to get the start Massive's inactive list does not carry. A ticker Massive does
not know on that day answers 404 (``None`` from the HTTP client): "not found", a marker the task
stores so it is not asked again.

Request key ``TICKER|YYYY-MM-DD`` (the ACT-style ticker, as ``MassiveOverview``'s; the date is the
day asked). The key goes in the ``Authorization`` header, the request waits on the shared
``massive`` limiter (free tier 12.5 s a request). Every field the answer holds is kept (owner
tenet 2026-11-01): identity (``list_date``, FIGIs, CIK, name, type, exchange, ``active``,
``delisted_date`` from ``delisted_utc``) and the company's other fields (market, locale, currency,
SIC, website, head count, description, ``last_updated_utc`` as received). Identity only: never a
feature.
"""

import json
from datetime import date
from typing import Any
from urllib.parse import quote

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.vendors.massive.client import HOST, _Massive, act_symbol
from algotrade_sources.vendors.massive.overview import massive_ticker

DETAILS = HOST + "/v3/reference/tickers/{ticker}?date={day}"
SEPARATOR = "|"
COLUMNS = [
    "ticker", "list_date", "name", "cik", "figi", "share_class_figi", "vendor_type", "exchange",
    "active", "delisted_date", "market", "locale", "currency_name", "last_updated_utc",
    "sic_code", "sic_description", "homepage_url", "total_employees", "description",
]  # fmt: skip


def details_key(ticker: str, day: date) -> str:
    """The request key asking for ``ticker`` as it was on ``day``."""
    return f"{ticker}{SEPARATOR}{day.isoformat()}"


def split_key(key: str) -> tuple[str, str]:
    """-> (ticker, ISO day) of a request key."""
    ticker, _, day = key.rpartition(SEPARATOR)
    if not ticker:
        raise ValueError(f"a details key is TICKER{SEPARATOR}YYYY-MM-DD, got {key!r}")
    return ticker, date.fromisoformat(day).isoformat()


def _text(value: Any) -> str | None:
    text = " ".join(str(value if value is not None else "").split())
    return text or None


def _day(value: Any) -> date | None:
    """The date part of an ISO date or timestamp (``delisted_utc``), ``None`` when unreadable."""
    text = _text(value)
    try:
        return None if text is None else date.fromisoformat(text[:10])
    except ValueError:
        return None


def parse_details(payload: bytes, ticker: str) -> pd.DataFrame:
    """One answer -> a one-row frame (``COLUMNS``; dates as ``date``, gaps ``None``). An answer
    without results still gives a row of nothing but the ticker."""
    r = json.loads(payload).get("results") or {}
    employees = r.get("total_employees")
    row = {
        "ticker": act_symbol(str(r.get("ticker") or ticker)),
        "list_date": _day(r.get("list_date")),
        "name": _text(r.get("name")),
        "cik": _text(r.get("cik")),
        "figi": _text(r.get("composite_figi")),
        "share_class_figi": _text(r.get("share_class_figi")),
        "vendor_type": _text(r.get("type")),
        "exchange": _text(r.get("primary_exchange")),
        "active": r.get("active") if isinstance(r.get("active"), bool) else None,
        "delisted_date": _day(r.get("delisted_utc")),
        "market": _text(r.get("market")),
        "locale": _text(r.get("locale")),
        "currency_name": _text(r.get("currency_name")),
        "last_updated_utc": _text(r.get("last_updated_utc")),
        "sic_code": _text(r.get("sic_code")),
        "sic_description": _text(r.get("sic_description")),
        "homepage_url": _text(r.get("homepage_url")),
        "total_employees": int(employees) if isinstance(employees, int | float) else None,
        "description": _text(r.get("description")),
    }
    return pd.DataFrame([row], columns=COLUMNS).astype(object).where(lambda f: f.notna(), None)


class MassiveTickerDetails(_Massive):
    """A ticker's record as of a day. Request key: ``TICKER|YYYY-MM-DD``."""

    dataset = "ticker_details"

    def fetch(self, request: FetchRequest) -> bytes | None:
        ticker, day = split_key(request.key)
        return self._get(DETAILS.format(ticker=quote(massive_ticker(ticker), safe=""), day=day))

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        ticker, _ = split_key(request.key)
        return Normalized(
            session_date=None, tables={}, parsed={"details": parse_details(payload, ticker)}
        )
